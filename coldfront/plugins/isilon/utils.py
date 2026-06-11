import logging

import isilon_sdk.v9_12_0 as isilon_api
from isilon_sdk.v9_12_0.rest import ApiException

from coldfront.core.utils.common import import_from_settings
from coldfront.core.allocation.models import AllocationAttributeType, AllocationAttribute
from coldfront.config.plugins.isilon import ISILON_AUTH_MODEL

logger = logging.getLogger(__name__)

if ISILON_AUTH_MODEL == 'ldap':
    try:
        from coldfront.plugins.ldap.utils import LDAPConn
    except:
        logger.warning("no ldap plugin; isilon auth model will have issues")

def get_isilon_url(resource):
    """Return the Isilon API URL from the `url` resource attribute."""
    if isinstance(resource, str):
        return resource

    value = resource.get_attribute('url', expand=False, typed=False)
    if value:
        return str(value).strip()

    raise ValueError(
        f"Missing required ResourceAttributeType 'url' for resource {resource.name}"
    )

class IsilonConnection:
    """Convenience class containing methods for collecting data from an isilon cluster
    """
    def __init__(self, url):
        self.cluster_name = url
        self.api_client = self.connect(url)
        # APIs
        self._auth_client = None
        self._namespace_client = None
        self._pools_client = None
        self._protocols_client = None
        self._quota_client = None
        self._snapshot_client = None
        # stats
        self._allocated_space = None
        self._total_space = None
        self._used_space = None

    def connect(self, url):
        configuration = isilon_api.Configuration()
        configuration.host = url
        configuration.username = import_from_settings('ISILON_USER')
        configuration.password = import_from_settings('ISILON_PASS')
        configuration.verify_ssl = False
        api_client = isilon_api.ApiClient(configuration)
        return api_client

    @property
    def quota_client(self):
        if not self._quota_client:
            self._quota_client = isilon_api.QuotaApi(self.api_client)
        return self._quota_client

    @property
    def auth_client(self):
        """Set up the Auth api.
        Useful AuthApi methods:
            list_auth_groups (doesn't access ldap groups)
            list_auth_users (doesn't access ldap users)
        """
        if not self._auth_client:
            self._auth_client = isilon_api.AuthApi(self.api_client)
        return self._auth_client

    @property
    def protocols_client(self):
        if not self._protocols_client:
            self._protocols_client = isilon_api.ProtocolsApi(self.api_client)
        return self._protocols_client

    @property
    def snapshot_client(self):
        if not self._snapshot_client:
            self._snapshot_client = isilon_api.SnapshotApi(self.api_client)
        return self._snapshot_client

    @property
    def namespace_client(self):
        """Set up the namespace api.
        Useful NamespaceApi methods:
            create_directory
            get_acl
            set_acl
        """
        if not self._namespace_client:
            self._namespace_client = isilon_api.NamespaceApi(self.api_client)
        return self._namespace_client

    @property
    def pools_client(self):
        if not self._pools_client:
            self._pools_client = isilon_api.StoragepoolApi(self.api_client)
        return self._pools_client

    @property
    def total_space(self):
        """total usable disk space"""
        if self._total_space is None:
            pool_query = self.pools_client.get_storagepool_storagepools(
                toplevels=True)
            pools_bytes = [int(sp.usage.usable_bytes) for sp in pool_query.storagepools]
            self._total_space = sum(pools_bytes)
        return self._total_space

    @property
    def allocated_space(self):
        """space claimed by allocations"""
        if self._allocated_space is None:
            quotas = self.quota_client.list_quota_quotas(type='directory')
            self._allocated_space = sum(
                [q.thresholds.hard for q in quotas.quotas if q.thresholds.hard])
        return self._allocated_space

    @property
    def used_space(self):
        """space used by files etc"""
        if self._used_space is None:
            pool_query = self.pools_client.get_storagepool_storagepools(
                toplevels=True)
            pools_bytes = [int(sp.usage.used_bytes) for sp in pool_query.storagepools]
            self._used_space = sum(pools_bytes)
        return self._used_space

    @property
    def unused_space(self):
        """total unused space on a volume"""
        return self.total_space - self.used_space

    @property
    def unallocated_space(self):
        """total unallocated space on a volume"""
        return self.total_space - self.allocated_space

    def to_tb(self, bytes_value):
        return bytes_value / (1024**4)

    def get_quota_from_path(self, path):
        current_quota = self.quota_client.list_quota_quotas(
            path=path, recurse_path_children=False, recurse_path_parents=False, type='directory')
        if len(current_quota.quotas) > 1:
            raise Exception(f'more than one quota returned for quota {self.cluster_name}:{path}')
        if len(current_quota.quotas) == 0:
            raise Exception(f'no quotas returned for quota {self.cluster_name}:{path}')
        return current_quota.quotas[0]

    def create_directory(self, path):
        try:
            self.namespace_client.create_directory(
                path,
                x_isi_ifs_target_type='container',
                overwrite=False,
            )
        except ApiException as e:
            logger.error("can't create directory: %s", e)
            if e.status == 403:
                logger.error("can't create directory %s, it already exists", path)
            raise

    def set_directory_acl(self, path, namespace_acl):
        try:
            self.namespace_client.set_acl(path, True, namespace_acl)
        except ApiException as e:
            logger.exception(
                "can't set directory acl. path=%s acl_obj=%s error=%s", path, namespace_acl, e
            )
            raise


class IsilonUser:
    """Class for retrieval and storage of an isilon user from a coldfront user
    """

    def __init__(self, user_obj, isilon_conn):
        self.name = user_obj.username
        self.django_user = user_obj
        self.isilon_conn = isilon_conn
        # self.isilon_user = self.return_isilon_user()
        self.uid = self.return_isilon_user_id()

    def return_isilon_user_id(self):
        if not ISILON_AUTH_MODEL:
            return self.isilon_conn.auth_client.list_auth_users(
                filter=self.name
            ).users[0].uid.id
        if ISILON_AUTH_MODEL == 'ldap': #and 'ldap' in plugins:
            ldap_conn = LDAPConn()
            return ldap_conn.return_user_by_name(self.name, attributes=['uidNumber'])['uidNumber'][0]


class IsilonGroup:
    """Class for retrieval and storage of an isilon user from a coldfront user
    """

    def __init__(self, group_obj, isilon_conn):
        self.name = group_obj.title
        self.django_group = group_obj
        self.isilon_conn = isilon_conn
        self.gid = self.return_isilon_group_id()

    def return_isilon_group_id(self):
        if not ISILON_AUTH_MODEL:
            return self.isilon_conn.auth_client.list_auth_users(
                filter=self.name
            ).groups[0].gid.id
        if ISILON_AUTH_MODEL == 'ldap': #and 'ldap' in plugins:
            ldap_conn = LDAPConn()
            return ldap_conn.return_group_by_name(self.name)['gidNumber'][0]


def create_isilon_subdirectory_structure(labroot_path, isilon_pi, isilon_group, isilon_conn):
    """create labroot_path/Lab and labroot_path/Everyone directories with correct ACLs
    Lab directory should be owned by the lab's PI and lab group with 2770 permissions
    Everyone directory should be owned by lab group and lab PI with 2775 permissions
    """
    everyone_path = f'{labroot_path}/Everyone'
    isilon_conn.create_directory(everyone_path)

    everyone_acl = isilon_api.NamespaceAcl(
        acl=[
            isilon_api.AclObject(# acl object for group permissions
                accessrights=['dir_gen_read','dir_gen_execute','file_gen_read','file_gen_execute'],
                inherit_flags=['object_inherit','container_inherit','inherit_only'],
                trustee=isilon_api.MemberObject(
                    id='SID:S-1-3-1', name='Creator Group', type='wellknown')
            ),
            isilon_api.AclObject(# acl object for owner permissions
                accessrights=['dir_gen_all'],
                inherit_flags=['object_inherit','container_inherit','inherit_only'],
                trustee=isilon_api.MemberObject(
                    id='SID:S-1-3-0', name='Creator Owner', type='wellknown'),
            ),
        ],
        group={'id': f'GID:{isilon_group.gid}'},
        owner={'id': f'UID:{isilon_pi.uid}'},
        authoritative='mode',
        mode='2775',
    )
    isilon_conn.set_directory_acl(everyone_path, everyone_acl)

    lab_path = f'{labroot_path}/Lab'
    isilon_conn.create_directory(lab_path)
    lab_acl = isilon_api.NamespaceAcl(
        acl=[
            isilon_api.AclObject(# acl object for group permissions
                accessrights=['dir_gen_read','dir_gen_execute','file_gen_read','file_gen_execute'],
                inherit_flags=['object_inherit','container_inherit','inherit_only'],
                trustee=isilon_api.MemberObject(
                    id='SID:S-1-3-1', name='Creator Group', type='wellknown')
            ),
            isilon_api.AclObject(# acl object for owner permissions
                accessrights=['dir_gen_all'],
                inherit_flags=['object_inherit','container_inherit','inherit_only'],
                trustee=isilon_api.MemberObject(
                    id='SID:S-1-3-0', name='Creator Owner', type='wellknown'),
            ),
        ],
        group={'id': f'GID:{isilon_group.gid}'},
        owner={'id': f'UID:{isilon_pi.uid}'},
        authoritative='mode',
        mode='2770',
    )
    isilon_conn.set_directory_acl(lab_path, lab_acl)
    return 'Everyone and Lab subdirectories created with ACLs'


def create_isilon_allocation_quota(
        allocation, resource, nfs_share=True, cifs_share=True
    ):
    """Create a new isilon allocation quota
    """
    lab_name = allocation.project.title
    isilon_resource = get_isilon_url(resource)
    isilon_conn = IsilonConnection(isilon_resource)
    actions_performed = []
    # determine whether rc_labs or rc_fasse_labs path
    subdir = 'rc_labs' # if 'fasse' not in isilon_resource else 'rc_fasse_labs'
    path = f'ifs/{subdir}/{lab_name}'
    root_uid = '0'

    ### Set ownership and default permissions ###
    isilon_pi = IsilonUser(allocation.project.pi, isilon_conn)
    isilon_group = IsilonGroup(allocation.project, isilon_conn)

    ### make the directory ###
    isilon_conn.create_directory(path)
    actions_performed.append('directory created')

    namespace_acl = isilon_api.NamespaceAcl(
        acl=[
            isilon_api.AclObject(# acl object for group permissions
                accessrights=['dir_gen_read','dir_gen_execute','file_gen_read','file_gen_execute'],
                inherit_flags=['object_inherit','container_inherit','inherit_only'],
                trustee=isilon_api.MemberObject(
                    id='SID:S-1-3-1', name='Creator Group', type='wellknown')
            ),
            isilon_api.AclObject(# acl object for owner permissions
                accessrights=['dir_gen_all'],
                inherit_flags=['object_inherit','container_inherit','inherit_only'],
                trustee=isilon_api.MemberObject(
                    id='SID:S-1-3-0', name='Creator Owner', type='wellknown'),
            ),
        ],
        group={'id': f'GID:{isilon_group.gid}'},
        owner={'id': f'UID:{root_uid}'},
        authoritative='mode',
        mode='2755',
    )
    isilon_conn.set_directory_acl(path, namespace_acl)
    actions_performed.append('acl set')

    ### Set up quota ###
    # make a threshold object with the hard quota
    threshold = isilon_api.QuotaQuotaThresholds(
        hard=int(allocation.size * 1024**4),
    )

    quota_quota = isilon_api.QuotaQuotaCreateParams(
        container=True,
        enforced=True,
        include_snapshots=False,
        path=f'/{path}',
        thresholds=threshold,
        thresholds_on='fslogicalsize',
        type='directory',
    )
    try:
        isilon_conn.quota_client.create_quota_quota(quota_quota)
    except:
        logger.error('quota creation failed')
        raise
    actions_performed.append('quota set')

    subdir_type = AllocationAttributeType.objects.get(name='Subdirectory')
    AllocationAttribute.objects.create(
        allocation=allocation,
        allocation_attribute_type_id=subdir_type.pk,
        value=f'{subdir}/{lab_name}'
    )

    option_exceptions = {}
    ### set up snapshots for the created quota ###
    snapshot_schedule = isilon_api.SnapshotScheduleCreateParams(
        name=lab_name,
        path=f'/{path}',
        pattern=f"{lab_name}_daily_%Y-%m-%d-_%H-%M",
        schedule="Every 1 days",
        duration=7*24*60*60,
    )
    try:
        isilon_conn.snapshot_client.create_snapshot_schedule(snapshot_schedule)
        actions_performed.append('snapshots scheduled')
    except Exception as e:
        option_exceptions['snapshots'] = e

    # if nfs_share:
    #     ### set up NFS export ###
    #     root_clients = import_from_settings('ISILON_NFS_ROOT_CLIENTS').split(',')
    #     if 'fasse' in path:
    #         clients = import_from_settings('ISILON_NFS_FASSE_CLIENTS').split(',')
    #     else:
    #         clients = import_from_settings('ISILON_NFS_CANNON_CLIENTS').split(',')

    #     nfs_export = isilon_api.NfsExportCreateParams(
    #         root_clients=root_clients,
    #         clients=clients,
    #         paths=[f'/{path}'],
    #     )
    #     try:
    #         isilon_conn.protocols_client.create_nfs_export(nfs_export)
    #         actions_performed.append('nfs share created')
    #     except Exception as e:
    #         option_exceptions['nfs_share'] = e

    if cifs_share:
        ### set up smb share ###
        smb_share = isilon_api.SmbShareCreateParams(
            create_permissions="inherit mode bits",
            name=lab_name,
            ntfs_acl_support=False,
            path=f'/{path}',
            permissions=[
                isilon_api.SmbSharePermission(
                    permission='change',
                    permission_type='allow',
                    trustee=isilon_api.MemberObject(
                        id=f'GID:{isilon_group.gid}',
                        name=isilon_group.name,
                        type='group',
                    ),
                ),
            ],
        )
        try:
            isilon_conn.protocols_client.create_smb_share(smb_share)
            actions_performed.append('smb share created')
        except Exception as e:
            option_exceptions['cifs_share'] = e

    try:
        subdir_structure = create_isilon_subdirectory_structure(
                path, isilon_pi, isilon_group, isilon_conn)
        actions_performed.append(subdir_structure)
    except Exception as e:
        option_exceptions['subdirectory_structure'] = e

    logger.info(
        'Auto-created Isilon allocation quota.',
        extra={
            'category': 'integration:isilon',
            'status': 'success',
            'project': lab_name,
            'resource': resource,
            'path': path,
            'allocation_id': allocation.pk,
            'actions_performed': actions_performed,
            'exceptions': option_exceptions,
        }
    )
    return option_exceptions


def update_isilon_allocation_quota(allocation, new_quota):
    """Update the quota for an allocation on an isilon cluster

    Parameters
    ----------
    api_instance : isilon_api.QuotaApi
    allocation : coldfront.core.allocation.models.Allocation
    quota : int
    """
    # make isilon connection to the allocation's resource
    resource = allocation.resources.first()
    isilon_resource = get_isilon_url(resource)
    isilon_conn = IsilonConnection(isilon_resource)
    path = f'/ifs/{allocation.path}'

    # check if enough space exists on the volume
    new_quota_bytes = new_quota * 1024**4
    unallocated_space = isilon_conn.unallocated_space
    current_quota_obj = isilon_conn.get_quota_from_path(path)
    current_quota = current_quota_obj.thresholds.hard
    logger.warning(
        'Preparing to change allocation quota.',
        extra={
            'path': allocation.path,
            'allocation_pk': allocation.pk,
            'current_quota': current_quota,
            'current_quota_tib': allocation.size,
            'new_quota': new_quota_bytes,
            'new_quota_tib': new_quota,
        }
    )
    if unallocated_space < (new_quota_bytes-current_quota):
        raise ValueError(
            f'insufficient space for new quota. resource={isilon_resource},'
            f'allocation_pk={allocation.pk},new_quota_tib={new_quota}'
        )
    if current_quota > new_quota_bytes:
        current_quota_usage = current_quota_obj.usage.physical
        space_needed = new_quota_bytes * .8
        if current_quota_usage > space_needed:
            raise ValueError(
                'Cannot automatically reduce allocation quota to less than 80% of space in use. '
                f'current_quota={allocation.size},new_quota={new_quota},'
                f'space_used={allocation.usage},allocation_pk={allocation.pk}'
            )
    try:
        new_quota_obj = {'thresholds': {'hard': new_quota_bytes}}
        isilon_conn.quota_client.update_quota_quota(new_quota_obj, current_quota_obj.id)
        print(f'SUCCESS: updated quota for {allocation} to {new_quota}')
        logger.info(
            'Updated quota.',
            extra={
                'category': 'integration:isilon',
                'status': 'success',
                'allocation_pk': allocation.pk,
                'resource': isilon_resource,
                'path': allocation.path,
                'new_quota': new_quota,
            }
        )
    except ApiException as e:
        logger.exception(
            'Quota update failed.',
            extra={
                'category': 'integration:isilon',
                'status': 'failure',
                'allocation_pk': allocation.pk,
                'new_quota': new_quota,
                'error': str(e),
            })
        err = f'ERROR: could not update quota for {allocation} to {new_quota} - {e}'
        print_log_error(e, err)
        raise

def print_log_error(e, message):
    print(f'ERROR: {message} - {e}')
    logger.error('%s - %s', message, e)

def delete_isilon_allocation(resource_url, path, force=False):
    """Delete an isilon allocation directory and all associated items created by
    ``create_isilon_allocation_quota``.

    Deletes, in order: snapshot schedule, SMB share, NFS export, quota, Lab and Everyone
    subdirectories, root lab directory. Items that do not exist are skipped gracefully.

    Fails before deleting anything if physical data is present in the Lab or Everyone
    subdirectories (quota ``usage.physical > 0``).

    Prints a preview of what will be deleted and requires explicit confirmation before
    proceeding.  Pass ``force=True`` to bypass the prompt in automated tests.

    Parameters
    ----------
    resource_url : str
        Isilon cluster URL (e.g. ``'https://isilon01.university.edu:8080'``).
    path : str
        Allocation path as stored in the ``Subdirectory`` attribute
        (e.g. ``'rc_labs/smithlab'``).  The lab name is derived from the last path component.
    force : bool
        Skip the confirmation prompt.  Defaults to ``False``.

    Raises
    ------
    ValueError
        If physical data is found in the Lab or Everyone subdirectories.
    """
    isilon_conn = IsilonConnection(resource_url)

    lab_name = path.rsplit('/', 1)[-1]
    root_path = f'/ifs/{path}'
    lab_path = f'{root_path}/Lab'
    everyone_path = f'{root_path}/Everyone'

    # ------------------------------------------------------------------
    # Discovery: find every item that actually exists on the cluster
    # ------------------------------------------------------------------
    to_delete = {}  # key → human label, used for the confirmation prompt
    deletion_plan = {}  # key → (callable, *args) executed during deletion

    # Quota (also used for the data-present check below)
    quota_obj = None
    try:
        quota_result = isilon_conn.quota_client.list_quota_quotas(
            path=root_path,
            recurse_path_children=False,
            recurse_path_parents=False,
            type='directory',
        )
        if quota_result.quotas:
            quota_obj = quota_result.quotas[0]
            hard_tib = quota_obj.thresholds.hard / 1024 ** 4 if quota_obj.thresholds.hard else 0
            to_delete['quota'] = f'Quota  {root_path}  (hard limit: {hard_tib:.1f} TiB)'
            deletion_plan['quota'] = (
                isilon_conn.quota_client.delete_quota_quota, quota_obj.id
            )
    except ApiException as e:
        logger.warning('Could not query quota for %s: %s', root_path, e)

    # Snapshot schedule (named after the lab)
    try:
        schedule_result = isilon_conn.snapshot_client.list_snapshot_schedules()
        matching = [s for s in (schedule_result.schedules or []) if s.name == lab_name]
        if matching:
            to_delete['snapshot'] = f'Snapshot schedule  "{lab_name}"  (path: {matching[0].path})'
            deletion_plan['snapshot'] = (
                isilon_conn.snapshot_client.delete_snapshot_schedule, lab_name
            )
    except ApiException as e:
        logger.warning('Could not list snapshot schedules: %s', e)

    # SMB share (named after the lab)
    try:
        smb_result = isilon_conn.protocols_client.list_smb_shares()
        matching_smb = [s for s in (smb_result.shares or []) if s.name == lab_name]
        if matching_smb:
            to_delete['smb'] = f'SMB share  "{lab_name}"  (path: {matching_smb[0].path})'
            deletion_plan['smb'] = (
                isilon_conn.protocols_client.delete_smb_share, lab_name
            )
    except ApiException as e:
        logger.warning('Could not list SMB shares: %s', e)

    # NFS export (matched by path prefix)
    try:
        nfs_result = isilon_conn.protocols_client.list_nfs_exports()
        matching_nfs = [
            x for x in (nfs_result.exports or [])
            if any(p == root_path or p.startswith(root_path + '/') for p in (x.paths or []))
        ]
        for export in matching_nfs:
            label = f'NFS export  id={export.id}  paths={export.paths}'
            to_delete[f'nfs_{export.id}'] = label
            deletion_plan[f'nfs_{export.id}'] = (
                isilon_conn.protocols_client.delete_nfs_export, export.id
            )
    except ApiException as e:
        logger.warning('Could not list NFS exports: %s', e)

    # Subdirectories and root directory (existence check via namespace)
    for dir_path, key, label in [
        (lab_path,      'dir_lab',      f'Directory  {lab_path}'),
        (everyone_path, 'dir_everyone', f'Directory  {everyone_path}'),
        (root_path,     'dir_root',     f'Directory  {root_path}'),
    ]:
        try:
            isilon_conn.namespace_client.get_directory_metadata(dir_path)
            to_delete[key] = label
            deletion_plan[key] = (isilon_conn.namespace_client.delete_directory, dir_path)
        except ApiException as e:
            if e.status == 404:
                pass  # directory does not exist; skip silently
            else:
                logger.warning('Could not check existence of %s: %s', dir_path, e)

    if not to_delete:
        print(f'Nothing found to delete for lab "{lab_name}" on {resource_url}.')
        return

    # ------------------------------------------------------------------
    # Data-present guard: refuse to proceed if Lab or Everyone have data
    # ------------------------------------------------------------------
    if quota_obj is not None:
        physical_bytes = getattr(quota_obj.usage, 'physical', None)
        if physical_bytes and physical_bytes > 0:
            raise ValueError(
                f'Refusing to delete: quota reports {physical_bytes:,} bytes of physical data '
                f'in {root_path}. Remove the data manually before running this function.'
            )

    # ------------------------------------------------------------------
    # Confirmation prompt
    # ------------------------------------------------------------------
    print(f'\nThe following items will be PERMANENTLY DELETED from {resource_url}:\n')
    for label in to_delete.values():
        print(f'  - {label}')
    print()

    if not force:
        answer = input('Type "yes" to confirm deletion, or anything else to abort: ').strip()
        if answer.lower() != 'yes':
            print('Aborted. Nothing was deleted.')
            return

    # ------------------------------------------------------------------
    # Deletion (snapshot → SMB → NFS → quota → Lab → Everyone → root)
    # ------------------------------------------------------------------
    ordered_keys = (
        ['snapshot', 'smb']
        + [k for k in deletion_plan if k.startswith('nfs_')]
        + ['quota', 'dir_lab', 'dir_everyone', 'dir_root']
    )
    for key in ordered_keys:
        if key not in deletion_plan:
            continue
        fn, *args = deletion_plan[key]
        label = to_delete[key]
        try:
            fn(*args)
            print(f'  Deleted: {label}')
            logger.info('delete_isilon_allocation: deleted %s', label)
        except ApiException as e:
            if e.status == 404:
                print(f'  Skipped (not found): {label}')
            else:
                print(f'  ERROR deleting {label}: {e}')
                logger.error('delete_isilon_allocation: error deleting %s: %s', label, e)

    print(f'\nDeletion complete for lab "{lab_name}" on {resource_url}.')


def update_coldfront_quota_and_usage(alloc, usage_attribute_type, value_list):
    usage_attribute, _ = alloc.allocationattribute_set.get_or_create(
        allocation_attribute_type=usage_attribute_type
    )
    usage_attribute.value = value_list[0]
    usage_attribute.save()
    usage = usage_attribute.allocationattributeusage
    usage.value = value_list[1]
    usage.save()
    return usage_attribute
