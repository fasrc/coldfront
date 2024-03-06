import logging

import isilon_sdk.v9_3_0 as isilon_api
from isilon_sdk.v9_3_0.rest import ApiException

from coldfront.core.utils.common import import_from_settings
from coldfront.config.plugins.isilon import ISILON_AUTH_MODEL

logger = logging.getLogger(__name__)

if ISILON_AUTH_MODEL == 'ldap':
    try:
        from coldfront.plugins.ldap.utils import LDAPConn
    except:
        logger.warning("no ldap plugin; isilon auth model will have issues")

class IsilonConnection:
    """Convenience class containing methods for collecting data from an isilon cluster
    """
    def __init__(self, cluster_name):
        self.cluster_name = cluster_name
        self.api_client = self.connect(cluster_name)
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

    def connect(self, cluster_name):
        configuration = isilon_api.Configuration()
        configuration.host = f'http://{cluster_name}01.rc.fas.harvard.edu:8080'
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
        self.name = group_obj.username
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


def create_isilon_allocation_quota(
        allocation, snapshots=True, nfs=True, cifs=False
    ):
    """Create a new isilon allocation quota
    """
    lab_name = allocation.project.title
    isilon_resource = allocation.resources.first().name.split('/')[0]
    isilon_conn = IsilonConnection(isilon_resource)

    # determine whether rc_labs or rc_fasse_labs path
    subdir = 'rc_fasse_labs' if '_l3' in lab_name else 'rc_labs'
    path = f'ifs/{subdir}/{lab_name}'

    ### make the directory ###
    try:
        isilon_conn.namespace_client.create_directory(
            path,
            x_isi_ifs_target_type='container',
            overwrite=False,
        )
    except ApiException as e:
        logger.error("can't create directory: %s", e)
        if e.status == 403:
            logger.error("can't create directory %s, it already exists", path)
        raise

    ### Set ownership and default permissions ###
    isilon_pi = IsilonUser(allocation.project.pi, isilon_conn)
    isilon_group = IsilonGroup(allocation.project, isilon_conn)

    namespace_acl = {
        'group':{'id': isilon_group.gid},
        'owner':{'id': isilon_pi.uid},
        'authoritative': 'mode',
        'mode': '2770',
    }
    isilon_conn.namespace_client.set_acl(path, True, namespace_acl)

    ### Set up quota ###
    # make a threshold object with the hard quota
    threshold = isilon_api.QuotaQuotaThresholds(
        hard=int(allocation.quota * 1024**4),
        percent_advisory=95,
    )

    # TO DO: set up an advisory excess notification

    quota_quota = isilon_api.QuotaQuotaCreateParams(
        container=True,
        enforced=True,
        include_snapshots=False,
        path=path,
        thresholds=threshold,
        thresholds_on='fslogicalsize',
        type='directory',
    )
    isilon_conn.quota_client.create_quota_quota(quota_quota)

    if snapshots:
        ### set up snapshots for the created quota ###
        snapshot_schedule = isilon_api.SnapshotScheduleCreateParams(
            name=lab_name,
            path=f'/{path}',
            pattern=f"{lab_name}_daily_%Y-%m-%d-_%H-%M",
            schedule="Every 1 days",
            duration=7*24*60*60,
        )
        isilon_conn.snapshot_client.create_snapshot_schedule(snapshot_schedule)

    if cifs:
        ### set up smb share ###
        smb_share = isilon_api.SmbShareCreateParams(
            create_permissions="inherit mode bits",
            name=lab_name,
            ntfs_acl_support=False,
            path=f'/{path}',
        )
        isilon_conn.protocols_client.create_smb_share(smb_share)


def update_isilon_allocation_quota(allocation, new_quota):
    """Update the quota for an allocation on an isilon cluster

    Parameters
    ----------
    api_instance : isilon_api.QuotaApi
    allocation : coldfront.core.allocation.models.Allocation
    quota : int
    """
    # make isilon connection to the allocation's resource
    isilon_resource = allocation.resources.first().name.split('/')[0]
    isilon_conn = IsilonConnection(isilon_resource)
    path = f'/ifs/{allocation.path}'

    # check if enough space exists on the volume
    new_quota_bytes = new_quota * 1024**4
    unallocated_space = isilon_conn.unallocated_space
    current_quota_obj = isilon_conn.get_quota_from_path(path)
    current_quota = current_quota_obj.thresholds.hard
    logger.warning("changing allocation %s %s from %s (%s TB) to %s (%s TB)",
       allocation.path, allocation, current_quota, allocation.size, new_quota_bytes, new_quota
    )
    if unallocated_space < (new_quota_bytes-current_quota):
        raise ValueError(
            'ERROR: not enough space on volume to set quota to %s TB for %s'
            % (new_quota, allocation)
        )
    if current_quota > new_quota_bytes:
        current_quota_usage = current_quota_obj.usage.physical
        space_needed = new_quota_bytes * .8
        if current_quota_usage > space_needed:
            raise ValueError(
                'ERROR: cannot automatically shrink the size of allocations to a quota smaller than 80 percent of the space in use. Current size: %s Desired size: %s Space used: %s Allocation: %s'
                % (allocation.size, new_quota, allocation.usage, allocation)
            )
    try:
        new_quota_obj = {'thresholds': {'hard': new_quota_bytes}}
        isilon_conn.quota_client.update_quota_quota(new_quota_obj, current_quota_obj.id)
        print(f'SUCCESS: updated quota for {allocation} to {new_quota}')
        logger.info('SUCCESS: updated quota for %s to %s', allocation, new_quota)
    except ApiException as e:
        err = f'ERROR: could not update quota for {allocation} to {new_quota} - {e}'
        print_log_error(e, err)
        raise

def print_log_error(e, message):
    print(f'ERROR: {message} - {e}')
    logger.error('%s - %s', message, e)

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
