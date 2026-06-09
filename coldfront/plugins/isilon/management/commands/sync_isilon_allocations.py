import logging
from datetime import datetime

from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError

from coldfront.core.allocation.models import (
    Allocation,
    AllocationAttribute,
    AllocationAttributeType,
    AllocationStatusChoice,
    AllocationUser,
    AllocationUserStatusChoice,
)
from coldfront.core.project.models import Project
from coldfront.core.resource.models import Resource
from coldfront.plugins.isilon.utils import (
    IsilonConnection,
    get_isilon_url,
    print_log_error,
    update_coldfront_quota_and_usage,
)

logger = logging.getLogger(__name__)

_DEACTIVATE_STATUSES = ("Active", "Pending Deactivation")
_OPEN_REQUEST_STATUSES = ("New", "In Progress", "Pending Activation", "On Hold")
_QUOTA_PATHS = ("/ifs/rc_labs/", "/ifs/rc_fasse_labs/")


class Command(BaseCommand):
    """Sync ColdFront allocation records with live isilon/powerscale quota data.

    For each isilon/powerscale resource:
    - Creates new allocation records for quotas found on the cluster with no
      matching ColdFront allocation.
    - Updates quota and usage attributes on existing allocations.
    - Sets allocations not found on the cluster (Active or Pending Deactivation)
      to Inactive.
    """

    help = "Sync isilon/powerscale allocation records with live cluster quota data"

    def handle(self, *args, **kwargs):
        quota_bytes_attrtype = AllocationAttributeType.objects.get(name="Quota_In_Bytes")
        quota_tib_attrtype = AllocationAttributeType.objects.get(name="Storage Quota (TiB)")
        subdir_attrtype = AllocationAttributeType.objects.get(name="Subdirectory")
        payment_attrtype = AllocationAttributeType.objects.get(name="RequiresPayment")

        status_active = AllocationStatusChoice.objects.get(name="Active")
        status_inactive = AllocationStatusChoice.objects.get(name="Inactive")
        alloc_user_status_active = AllocationUserStatusChoice.objects.get(name="Active")

        isilon_resources = Resource.objects.filter(
            resourceattribute__value__in=("isilon", "powerscale")
        )

        for resource in isilon_resources:
            report = {
                "created": 0,
                "updated": 0,
                "deactivated": 0,
                "skipped_no_project": [],
                "skipped_open_request": [],
                "errors": [],
            }
            resource_url = get_isilon_url(resource)

            try:
                api = IsilonConnection(resource_url)
            except Exception as e:
                message = f"Could not connect to {resource_url} — skipping"
                print_log_error(e, message)
                continue

            # Step A: fetch all live quotas from the cluster
            live_quotas = {}
            try:
                for quota_path in _QUOTA_PATHS:
                    result = api.quota_client.list_quota_quotas(
                        path=quota_path, recurse_path_children=True
                    )
                    for q in result.quotas:
                        live_quotas[q.path] = q
            except Exception as e:
                message = f"Could not fetch quotas from {resource_url} — skipping"
                print_log_error(e, message)
                continue

            # Step B: create allocations for live quotas with no ColdFront record
            for quota_path, quota_obj in live_quotas.items():
                # path is like /ifs/rc_labs/labname — strip leading /ifs/
                relative_path = quota_path.removeprefix("/ifs/")
                path_parts = relative_path.strip("/").split("/")
                if len(path_parts) < 2:
                    continue
                lab_name = path_parts[1]

                try:
                    project = Project.objects.get(title=lab_name)
                except Project.DoesNotExist:
                    logger.warning(
                        "No project found for isilon path %s (lab=%s) — skipping",
                        quota_path,
                        lab_name,
                    )
                    report["skipped_no_project"].append(quota_path)
                    continue

                # Check whether an allocation already exists for this path
                existing = project.allocation_set.filter(
                    resources=resource,
                    allocationattribute__allocation_attribute_type=subdir_attrtype,
                    allocationattribute__value=relative_path,
                ).exclude(status__name="Merged")
                if existing.exists():
                    continue  # handled in Step C

                # Skip if there is an open allocation request for this resource
                if project.allocation_set.filter(
                    status__name__in=_OPEN_REQUEST_STATUSES, resources=resource
                ).exists():
                    logger.info(
                        "Open allocation request exists for project %s on %s — skipping creation",
                        lab_name,
                        resource_url,
                    )
                    report["skipped_open_request"].append(quota_path)
                    continue

                try:
                    quota_bytes = quota_obj.thresholds.hard or 0
                    quota_tib = quota_bytes / 1024**4
                    usage_bytes = quota_obj.usage.fslogical or 0
                    usage_tib = usage_bytes / 1024**4

                    allocation = Allocation.objects.create(
                        project=project,
                        status=status_active,
                        start_date=datetime.now(),
                        is_changeable=resource.is_allocatable,
                        justification=f"Allocation Information for {lab_name}",
                    )
                    allocation.resources.add(resource)

                    AllocationAttribute.objects.create(
                        allocation=allocation,
                        allocation_attribute_type=subdir_attrtype,
                        value=relative_path,
                    )
                    AllocationAttribute.objects.create(
                        allocation=allocation,
                        allocation_attribute_type=quota_bytes_attrtype,
                        value=quota_bytes,
                    )
                    AllocationAttribute.objects.create(
                        allocation=allocation,
                        allocation_attribute_type=quota_tib_attrtype,
                        value=quota_tib,
                    )
                    AllocationAttribute.objects.create(
                        allocation=allocation,
                        allocation_attribute_type=payment_attrtype,
                        value=resource.requires_payment,
                    )

                    try:
                        AllocationUser.objects.get_or_create(
                            allocation=allocation,
                            user=project.pi,
                            defaults={"status": alloc_user_status_active},
                        )
                    except ValidationError as e:
                        logger.warning(
                            "Could not add PI %s to allocation %s: %s",
                            project.pi.username,
                            allocation.pk,
                            e,
                        )

                    logger.info(
                        "Created allocation for %s on %s (path=%s)",
                        lab_name,
                        resource_url,
                        relative_path,
                    )
                    report["created"] += 1

                except Exception as e:
                    message = f"Error creating allocation for {quota_path} on {resource_url}"
                    print_log_error(e, message)
                    report["errors"].append(quota_path)

            # Step C: update quota and usage for existing allocations
            existing_allocations = Allocation.objects.filter(
                resources=resource,
                status__name__in=_DEACTIVATE_STATUSES,
            )
            for allocation in existing_allocations:
                alloc_path = f"/ifs/{allocation.path}" if allocation.path else None
                if not alloc_path or alloc_path not in live_quotas:
                    continue  # not found — handled in Step D

                quota_obj = live_quotas[alloc_path]
                quota_bytes = quota_obj.thresholds.hard
                usage_bytes = quota_obj.usage.fslogical
                if quota_bytes is None:
                    logger.warning(
                        "No hard threshold for allocation %s (path=%s) — skipping update",
                        allocation.pk,
                        alloc_path,
                    )
                    continue

                quota_tib = quota_bytes / 1024**4
                usage_tib = usage_bytes / 1024**4 if usage_bytes else 0

                try:
                    update_coldfront_quota_and_usage(
                        allocation, quota_bytes_attrtype, [quota_bytes, usage_bytes or 0]
                    )
                    update_coldfront_quota_and_usage(
                        allocation, quota_tib_attrtype, [quota_tib, usage_tib]
                    )
                    report["updated"] += 1
                except Exception as e:
                    message = f"Error updating allocation {allocation.pk} (path={alloc_path})"
                    print_log_error(e, message)
                    report["errors"].append(str(allocation.pk))

            # Step D: deactivate allocations not found on the cluster
            for allocation in existing_allocations:
                alloc_path = f"/ifs/{allocation.path}" if allocation.path else None
                if alloc_path and alloc_path in live_quotas:
                    continue  # found — already handled above

                allocation.status = status_inactive
                allocation.save()
                logger.warning(
                    "Deactivated allocation %s (path=%s) — not found on %s",
                    allocation.pk,
                    allocation.path,
                    resource_url,
                )
                report["deactivated"] += 1

            self.stdout.write(
                f"sync_isilon_allocations report for {resource_url}: {report}"
            )
            logger.warning("sync_isilon_allocations report for %s: %s", resource_url, report)
