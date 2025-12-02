"""Classes and utilities for managing associations between Coldfront and Slurm entities."""
import logging

from django.utils import timezone

from coldfront.core.utils.common import import_from_settings
from coldfront.core.allocation.models import (
    Allocation,
    AllocationAttributeType,
)
from coldfront.core.allocation.utils import get_or_create_allocation

from coldfront.core.project.models import Project
from coldfront.core.resource.models import (
    Resource, ResourceAttributeType, ResourceType, ResourceAttribute
)
from coldfront.plugins.slurmrest.utils import (
    SlurmApiConnection,
    SlurmError,
)
SLURMREST_CLUSTER_ATTRIBUTE_NAME = import_from_settings(
        'SLURMREST_CLUSTER_ATTRIBUTE_NAME', 'slurm_cluster')
SLURMREST_ACCOUNT_ATTRIBUTE_NAME = import_from_settings(
        'SLURMREST_ACCOUNT_ATTRIBUTE_NAME', 'slurm_account_name')
SLURMREST_SPECS_ATTRIBUTE_NAME = import_from_settings(
        'SLURMREST_SPECS_ATTRIBUTE_NAME', 'slurm_specs')
SLURMREST_USER_SPECS_ATTRIBUTE_NAME = import_from_settings(
        'SLURMREST_USER_SPECS_ATTRIBUTE_NAME', 'slurm_user_specs')
SLURM_IGNORE_USERS = import_from_settings('SLURMREST_IGNORE_USERS', [])
SLURM_IGNORE_ACCOUNTS = import_from_settings('SLURMREST_IGNORE_ACCOUNTS', [])
SLURM_NOOP = import_from_settings('SLURMREST_NOOP', False)
logger = logging.getLogger(__name__)

class ClusterResourceManager:
    """Class to manage Coldfront Resource objects corresponding to Slurm cluster entities."""
    def __init__(self, cluster_name):
        # connection
        self.cluster_name = cluster_name
        self.slurm_api = SlurmApiConnection(cluster_name)
        # slurm data caches
        self._accounts = None
        self._partitions = None
        self._nodes = None
        # coldfront resource caches
        self._cluster_resource = None

        self.partition_resource_type = ResourceType.objects.get(name='Cluster Partition')
        self.node_resource_type = ResourceType.objects.get(name='Compute Node')

        self.owner_attribute_type = ResourceAttributeType.objects.get(name='Owner')
        self.features_attribute_type = ResourceAttributeType.objects.get(name='Features')
        self.gpu_count_attribute_type = ResourceAttributeType.objects.get(name='GPU Count')
        self.core_count_attribute_type = ResourceAttributeType.objects.get(name='Core Count')
        self.service_end_attribute_type = ResourceAttributeType.objects.get(name='ServiceEnd')
        self.slurm_specs_resourceattribute_type = ResourceAttributeType.objects.get(
            name=SLURMREST_SPECS_ATTRIBUTE_NAME)
        self.account_attribute_type = AllocationAttributeType.objects.get(
            name=SLURMREST_ACCOUNT_ATTRIBUTE_NAME)
        self.cloud_acct_name_allocattrtype = AllocationAttributeType.objects.get(
            name='Cloud Account Name')
        self.hours_allocattrtype = AllocationAttributeType.objects.get(
            name='Core Usage (Hours)')


    ### Properties to lazily load Slurm data and Coldfront resources ###
    @property
    def accounts(self):
        """Retrieve and cache the list of Slurm accounts from the cluster."""
        if self._accounts is None:
            account_data = self.slurm_api.get_accounts()['accounts']
            self._accounts = [a for a in account_data if a['name'] not in SLURM_IGNORE_ACCOUNTS]
        return self._accounts

    @property
    def partitions(self):
        """Retrieve and cache the list of Slurm partitions from the cluster."""
        if self._partitions is None:
            self._partitions = self.slurm_api.get_partitions()['partitions']
        return self._partitions

    @property
    def nodes(self):
        """Retrieve and cache the list of Slurm nodes from the cluster."""
        if self._nodes is None:
            self._nodes = self.slurm_api.get_nodes()['nodes']
        return self._nodes

    @property
    def cluster_resource(self):
        """Retrieve or create the Coldfront Resource representing the Slurm cluster."""
        if self._cluster_resource is None:
            cluster_resource = Resource.objects.filter(
                resourceattribute__value=self.cluster_name,
                resource_type__name='Cluster'
            ).first()
            if not cluster_resource:
                raise SlurmError(f"Cluster resource for {self.cluster_name} not found.")
            self._cluster_resource = cluster_resource
        return self._cluster_resource


    ### Partition import methods ###
    def import_partition_data(self):
        """Import Slurm partitions as Coldfront Resources."""
        for partition in self.partitions:
            partition_resource = self.create_update_partition_resource(partition)
            self.update_partition_resource_allocations(partition, partition_resource)

    def create_update_partition_resource(self, partition_data):
        """Create or update a Coldfront Resource for a Slurm partition.
        Slurm partition Resource names are formatted as "<cluster_name>:<partition_name>"
        to ensure uniqueness in the ColdFront database.
        """
        partition_resource, created = Resource.objects.get_or_create(
            name=f'{self.cluster_name}:{partition_data["name"]}',
            parent_resource=self.cluster_resource,
            resource_type=self.partition_resource_type,
            defaults={
                'description': f"{partition_data['name']} partition on {self.cluster_name}"
            }
        )
        partition_resource.resourceattribute_set.update_or_create(
            resource_attribute_type=self.slurm_specs_resourceattribute_type,
            defaults={'value': partition_data['tres']['billing_weights']}
        )
        if created:
            logger.info("Created new partition resource: %s", partition_resource.name)
        return partition_resource

    def update_partition_resource_allocations(self, partition_data, partition_resource):
        """Update allocations to include partition resources based on access lists."""
        # identify the partition accounts
        partition_account_names = self.id_partition_projects(partition_data)
        # Retrieve all projects that have the same name as the resource accounts
        matching_projects = Project.objects.filter(title__in=partition_account_names)
        # collect allocations that have this resource
        matching_allocations = Allocation.objects.filter(resources=partition_resource)
        # remove allocations for projects no longer on the partition access list
        for allocation in matching_allocations:
            if allocation.project not in matching_projects:
                allocation.resources.remove(partition_resource)
        # add allocations for projects newly added to the partition access list
        allocations_missing_partition = Allocation.objects.filter(
                project__in=matching_projects, resources=self.cluster_resource
        ).exclude(resources=partition_resource)
        for allocation in allocations_missing_partition:
            allocation.resources.add(partition_resource)

    def id_partition_projects(self, partition_data):
        """identify the partition projects
        Crossreference Allow/DenyAccounts and Allow/DenyGroups.
        Projects must be permitted on both lists to access a given partition.
        """
        # identify allowed_groups
        all_slurm_account_names = [a['name'] for a in self.accounts]
        allowed_groups = partition_data['groups'].get('allowed', '').split(',')
        denied_accounts = partition_data['accounts'].get('deny', '').split(',')
        # if 'cluster_users' is in allowed_groups, then all users/accounts are allowed
        if 'cluster_users' in allowed_groups:
            partition_account_names = [
                        a for a in all_slurm_account_names if a not in denied_accounts]
        else:
            allowed_accounts = partition_data['accounts'].get('allowed', 'NA').split(',')
            if allowed_accounts == ['ALL']:
                partition_account_names = allowed_groups
            elif allowed_accounts == ['NA']:
                partition_account_names = [a for a in allowed_groups if a not in denied_accounts]
            else:
                partition_account_names = set(allowed_groups + allowed_accounts)
        return partition_account_names


    ### Node import methods ###
    def import_node_data(self):
        """Import Slurm nodes as Coldfront Resources.
        Include import of features, owner, core count, gpu count, etc.
        """
        for node in self.nodes:
            self.create_update_node_resource(node)
        for resource_to_delete in Resource.objects.filter(
            parent_resource=self.cluster_resource,
            resource_type=self.node_resource_type,
            is_available=True,
        ).exclude(name__in=[n['name'] for n in self.nodes]):
            logger.info("Node resource %s no longer exists in Slurm cluster %s; marking unavailable.",
                resource_to_delete.name, self.cluster_name
            )
            resource_to_delete.is_available = False
            resource_to_delete.save()
            ResourceAttribute.objects.update_or_create(
                resource=resource_to_delete,
                resource_attribute_type=self.service_end_attribute_type,
                defaults={'value':timezone.now()}
            )

    def create_update_node_resource(self, node_data):
        """Create or update a Coldfront Resource for a Slurm node."""
        # create or get the node resource
        node_resource, created = Resource.objects.get_or_create(
            name=node_data['name'],
            resource_type=self.node_resource_type,
            defaults={
                'parent_resource': self.cluster_resource,
                'description': f"Node {node_data['name']} on {self.cluster_resource.name}",
            }
        )
        # create or update resource attributes
        node_resource.resourceattribute_set.update_or_create(
            resource_attribute_type=self.features_attribute_type,
            defaults={'value': ','.join(node_data['features'])}
        )
        tres = node_data.get('tres_used', 0)
        if tres != 0:
            tres_dict = dict([i.split('=') for i in tres.split(',')])
            gpu_count = tres_dict.get('gres/gpu', 0)
            node_resource.resourceattribute_set.update_or_create(
                resource_attribute_type=self.gpu_count_attribute_type,
                defaults={'value': str(gpu_count)}
            )
        node_resource.resourceattribute_set.update_or_create(
            resource_attribute_type=self.core_count_attribute_type,
            defaults={'value': str(node_data.get('cores', 0))}
        )
        # owner sometimes needs to be set manually, so we don't update it if it exists
        node_resource.resourceattribute_set.get_or_create(
            resource_attribute_type=self.owner_attribute_type,
            defaults={'value': node_data.get('owner', 'unknown')}
        )
        if created:
            logger.info("Created new node resource: %s", node_resource.name)
        else:
            if node_resource.parent_resource != self.cluster_resource:
                logger.info("changing parent_resource of %s from %s to %s",
                    node_resource.name, node_resource.parent_resource, self.cluster_resource)
                node_resource.parent_resource = self.cluster_resource
                node_resource.is_available = True
                node_resource.save()
        return node_resource


    ### Allocation import methods ###
    def import_account_data(self):
        """Import Slurm accounts as Coldfront Allocations."""
        for account in self.accounts:
            self.create_update_account_allocation(account)


    def create_update_account_allocation(self, account_data):
        """
        Given a Slurm account name and cluster name, get or create the corresponding
        Coldfront Allocation object.  The Allocation is linked to the given Resource.
        """
        account_name = account_data['name']
        try:
            project = Project.objects.get(title=account_name)
        except Project.DoesNotExist:
            raise SlurmError(
                f"Unable to find Project for cluster {self.cluster_name} account {account_name}"
            )
        allocation, created = get_or_create_allocation(
            project_obj=project,
            resource_obj=self.cluster_resource,
        )
        # Add account-related attributes to the allocation
        allocation.allocationattribute_set.get_or_create(
            allocation_attribute_type=self.account_attribute_type,
            defaults={'value': account_name},
        )
        allocation.allocationattribute_set.get_or_create(
            allocation_attribute_type=self.cloud_acct_name_allocattrtype,
            defaults={'value': account_name}
        )
        allocation.allocationattribute_set.get_or_create(
            allocation_attribute_type=self.hours_allocattrtype,
            defaults={'value': 0}
        )
        return allocation
