import logging

from django.utils import timezone
from vastpy import VASTClient, RESTFailure

from coldfront.core.utils.common import import_from_settings
from coldfront.core.allocation.models import (
    Allocation,
    AllocationAttribute,
    AllocationAttributeType,
    AllocationStatusChoice,
)
from coldfront.core.project.models import Project
from coldfront.config.plugins.vast import VASTUSER, VASTPASS, VASTADDRESS, VASTAUTHORIZER

logger = logging.getLogger(__name__)

if VASTAUTHORIZER == 'AD':
    try:
        from coldfront.plugins.ldap.utils import LDAPConn
    except ImportError:
        logger.warning("no ldap plugin; vast group resolution will have issues")

class _LazyVastClient:
    """Defers VASTClient construction (which requires live VASTUSER/VASTPASS/
    VASTADDRESS credentials) until first use, so importing this module - needed
    just to discover/import vast/tests.py under `manage.py test` - doesn't
    require those credentials to be configured.
    """
    _instance = None

    def __getattr__(self, name):
        if self._instance is None:
            self._instance = VASTClient(address=VASTADDRESS, user=VASTUSER, password=VASTPASS)
        return getattr(self._instance, name)


client = _LazyVastClient()


class VastDirectoryQuota:
    """Wraps a raw VAST userquotas API response dict with the fields
    sync_vast_allocations needs. vastpy is an untyped REST passthrough, so quota
    data arrives as plain dicts rather than SDK objects.

    Unlike Isilon's SmartQuotas, VAST quotas are per-entity limits configured
    against one shared view path - `path` does not vary per group/project (every
    quota under a resource reports the same top-level path), so it is NOT a valid
    per-allocation identity key. Allocation identity for VAST is (project,
    resource); `path` here is kept only for logging.
    """
    def __init__(self, quota_dict):
        self.quota_dict = quota_dict
        self.path = quota_dict['path']
        self.entity = quota_dict.get('entity', {})
        hard_limit = quota_dict.get('hard_limit')
        self.has_hard_limit = hard_limit is not None
        self.hard_limit_bytes = hard_limit
        self.usage_bytes = quota_dict.get('used_capacity', 0)


def is_vast_path_ignored(path):
    """Return True if `path` is in the VAST_PATH_IGNORE setting."""
    return path in import_from_settings('VAST_PATH_IGNORE', [])


def get_vast_directory_stat(path):
    """Check whether `path` exists on the VAST filesystem via folders.stat_path.

    Returns the stat dict if the directory is present, or None if VAST reports
    it as not found. Any other failure (auth, network, etc.) is re-raised
    rather than treated as "absent", so a transient API problem can never be
    mistaken for a missing directory and wrongly skip/deactivate an allocation.
    """
    try:
        return client.folders.stat_path.post(path=path)
    except RESTFailure as e:
        if e.status == 503:
            return None
        raise


def get_vast_quota_group(quota_dict, ldap_conn=None):
    """Return the name of the group that owns a VAST userquota: resolves an AD gid
    via LDAP, or uses the groupname identifier directly. Returns None if the
    identifier type is unhandled or an AD group can't be resolved.
    """
    entity = quota_dict.get('entity', {})
    identifier_type = entity.get('identifier_type')

    if VASTAUTHORIZER == 'AD' and identifier_type == 'gid':
        gid = entity.get('identifier')
        group_result = ldap_conn.search_groups({'gidNumber': gid}, attributes=['sAMAccountName'])
        if group_result:
            return group_result[0]['sAMAccountName'][0]
        logger.warning("could not find matching AD group for quota %s", quota_dict)
        return None

    if identifier_type == 'groupname':
        return entity.get('identifier')

    logger.warning("Unhandled identifier type: %s", identifier_type)
    return None


def find_matching_pending_allocation(project, resource, quota_bytes):
    """Find an open allocation request (New/On Hold/In Progress/Pending Activation) for
    `project`/`resource` whose requested quota size matches `quota_bytes` and that
    doesn't already have a Subdirectory attribute set.
    """
    pending_statuses = import_from_settings(
        'PENDING_ALLOCATION_STATUSES', ['New', 'In Progress', 'On Hold', 'Pending Activation']
    )
    quota_tib = quota_bytes / 1024**4
    candidates = project.allocation_set.filter(
        resources=resource, status__name__in=pending_statuses,
    ).exclude(
        allocationattribute__allocation_attribute_type__name='Subdirectory'
    )
    for candidate in candidates:
        bytes_value = candidate.get_attribute('Quota_In_Bytes', typed=False)
        if bytes_value is not None and int(float(bytes_value)) == int(quota_bytes):
            return candidate
        tib_value = candidate.get_attribute('Storage Quota (TiB)', typed=False)
        if tib_value is not None and abs(float(tib_value) - quota_tib) < 0.01:
            return candidate
    return None


def update_allocation_quota_and_usage(allocation, quota_bytes, usage_bytes):
    """Update Quota_In_Bytes and Storage Quota (TiB) attributes/usage on `allocation`.

    Only rewrites the quota value when it has actually changed, to avoid noisy
    HistoricalRecords churn on every sync run; usage is always refreshed.
    Returns True if the quota value changed.
    """
    quota_bytes_type = AllocationAttributeType.objects.get(name='Quota_In_Bytes')
    quota_tib_type = AllocationAttributeType.objects.get(name='Storage Quota (TiB)')
    quota_tib = quota_bytes / 1024**4
    usage_tib = usage_bytes / 1024**4

    bytes_attr = allocation.allocationattribute_set.filter(
        allocation_attribute_type=quota_bytes_type
    ).first()
    quota_changed = bytes_attr is None or int(float(bytes_attr.value)) != int(quota_bytes)

    for attr_type, quota_value, usage_value in (
        (quota_bytes_type, quota_bytes, usage_bytes),
        (quota_tib_type, quota_tib, usage_tib),
    ):
        if quota_changed:
            attr, _ = allocation.allocationattribute_set.get_or_create(allocation_attribute_type=attr_type)
            attr.value = quota_value
            attr.save()
            attr.allocationattributeusage.value = usage_value
            attr.allocationattributeusage.save()
        else:
            allocation.set_usage(attr_type.name, usage_value)
    return quota_changed


def sync_allocation_for_vast_quota(project, resource, resource_url, directory_quota, report):
    """Reconcile a single VAST userquota (already matched to `project`) with
    ColdFront allocation state: update an existing Allocation, activate a matching
    pending allocation request, or create a new Allocation.

    Identity here is (project, resource), NOT the quota's path - see
    VastDirectoryQuota's docstring for why. A Subdirectory attribute is still
    set, using the synthetic 'C/{project.title}' path convention (matching the
    real on-disk layout under each VAST view), but only when one isn't already
    present, and it's never used to look allocations up.

    A new allocation is only created/activated if the project's directory is
    confirmed present on VAST (via folders.stat_path) - an existing Active
    allocation whose directory has since disappeared is left for
    deactivate_allocations_with_missing_directory to catch, not handled here.
    """
    subdir_type = AllocationAttributeType.objects.get(name='Subdirectory')
    requires_payment_type = AllocationAttributeType.objects.get(name='RequiresPayment')
    quota_bytes = directory_quota.hard_limit_bytes
    usage_bytes = directory_quota.usage_bytes
    placeholder_path = f'C/{project.title}'

    existing_allocation = Allocation.objects.filter(
        project=project, resources=resource, status__name=['Active', 'Pending Deactivation', 'Inactive']
    ).first()
    if existing_allocation:
        if existing_allocation.status.name == 'Active':
            update_allocation_quota_and_usage(existing_allocation, quota_bytes, usage_bytes)
            if not existing_allocation.path:
                AllocationAttribute.objects.get_or_create(
                    allocation=existing_allocation,
                    allocation_attribute_type=subdir_type,
                    defaults={'value': placeholder_path},
                )
            report['updated'].append(project.title)
        return existing_allocation

    if get_vast_directory_stat(f'/{resource_url}/{placeholder_path}') is None:
        logger.warning(
            'Directory %s not found on %s for project %s - not creating an allocation',
            placeholder_path, resource.name, project.title,
        )
        report['directory_missing'].append(project.title)
        return None

    pending_allocation = find_matching_pending_allocation(project, resource, quota_bytes)
    if pending_allocation:
        if not pending_allocation.path:
            AllocationAttribute.objects.get_or_create(
                allocation=pending_allocation,
                allocation_attribute_type=subdir_type,
                defaults={'value': placeholder_path},
            )
        pending_allocation.status = AllocationStatusChoice.objects.get(name='Active')
        if not pending_allocation.start_date:
            pending_allocation.start_date = timezone.now().date()
        pending_allocation.save()
        AllocationAttribute.objects.update_or_create(
            allocation=pending_allocation,
            allocation_attribute_type=requires_payment_type,
            defaults={'value': resource.requires_payment},
        )
        update_allocation_quota_and_usage(pending_allocation, quota_bytes, usage_bytes)
        report['activated'].append(project.title)
        return pending_allocation

    new_allocation = Allocation.objects.create(
        project=project,
        status=AllocationStatusChoice.objects.get(name='Active'),
        start_date=timezone.now().date(),
        is_changeable=True,
        justification=f'Auto-created by sync_vast_allocations for {project.title}',
    )
    new_allocation.resources.add(resource)
    AllocationAttribute.objects.create(
        allocation=new_allocation, allocation_attribute_type=subdir_type, value=placeholder_path,
    )
    AllocationAttribute.objects.create(
        allocation=new_allocation, allocation_attribute_type=requires_payment_type,
        value=resource.requires_payment,
    )
    update_allocation_quota_and_usage(new_allocation, quota_bytes, usage_bytes)
    report['created'].append(project.title)
    return new_allocation


def deactivate_allocations_with_missing_directory(resource, resource_url, found_projects, report):
    """Deactivate Active allocations on `resource` whose backing directory no
    longer exists on VAST, checked directly via folders.stat_path.

    This is deliberately not driven by presence in the userquotas list -
    quota-list membership isn't authoritative about whether the directory
    itself still exists (that's what caused the original mismatched-allocation
    bug), so every Active allocation is checked here regardless of whether its
    project appeared in this run's userquotas.
    """
    inactive_status = AllocationStatusChoice.objects.get(name='Inactive')
    pending_deactivation_status = AllocationStatusChoice.objects.get(name='Pending Deactivation')
    active_allocations = Allocation.objects.filter(resources=resource, status__name__in=['Active', 'Pending Deactivation'])
    for allocation in active_allocations:
        path = allocation.path or f'C/{allocation.project.title}'
        if get_vast_directory_stat(f'/{resource_url}/{path}') is not None:
            continue
        if allocation.project.title in found_projects:
            allocation.status = pending_deactivation_status
            allocation.save        
            logger.warning(
                'Marked vast allocation as "Pending Deactivation". pk=%s project=%s resource=%s directory=%s',
                allocation.pk, allocation.project.title, resource.name, path,
            )
            report['deactivation_slated'].append(allocation.project.title)
            continue
        allocation.status = inactive_status
        allocation.save()
        logger.warning(
            'Deactivating vast allocation. pk=%s project=%s resource=%s directory=%s',
            allocation.pk, allocation.project.title, resource.name, path,
        )
        report['deactivated'].append(allocation.project.title)


def sync_vast_resource_allocations(resource):
    """Sync all VAST userquotas with a hard limit on `resource` into ColdFront
    Allocations, and deactivate Active allocations whose directory no longer
    exists on VAST. Returns a report dict summarizing what happened.
    """
    report = {
        'created': [],
        'activated': [],
        'updated': [],
        'deactivated': [],
        'deactivation_slated': [],
        'missing_projects': [],
        'unresolved_group': [],
        'no_limit': [],
        'directory_missing': [],
    }
    resource_url = resource.get_attribute('url', expand=False, typed=False)
    quotas = client.userquotas.get(
        entity__is_group=True,
        path__startswith=f'/{resource_url}',
    )

    ldap_conn = LDAPConn() if VASTAUTHORIZER == 'AD' else None
    found_projects = set()

    for quota_dict in quotas:
        directory_quota = VastDirectoryQuota(quota_dict)

        group_name = get_vast_quota_group(quota_dict, ldap_conn)
        if not group_name:
            logger.warning(
                'Could not resolve an owning group for a quota on %s: %s', resource.name, quota_dict
            )
            report['unresolved_group'].append(directory_quota.path)
            continue

        project = Project.objects.filter(title=group_name).first()
        if project is None:
            report['missing_projects'].append(group_name)
            continue

        # count the project as "seen" before the hard-limit check, so an existing
        # allocation isn't deactivated just because its quota currently has no
        # hard limit set
        found_projects.add(project.title)

        if not directory_quota.has_hard_limit:
            if not is_vast_path_ignored(directory_quota.path):
                logger.warning('No hard quota limit set for a quota on %s: %s', resource.name, quota_dict)
                report['no_limit'].append(directory_quota.path)
            continue

        sync_allocation_for_vast_quota(project, resource, resource_url, directory_quota, report)

    deactivate_allocations_with_missing_directory(resource, resource_url, found_projects, report)

    return report
