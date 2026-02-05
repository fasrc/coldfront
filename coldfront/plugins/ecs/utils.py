import logging

from ecsclient.client import Client

from coldfront.core.utils.common import import_from_settings

ECS_CLIENT_VERSION = import_from_settings('ECS_CLIENT_VERSION', '3')
ECS_USER = import_from_settings('ECS_USER')
ECS_PASS = import_from_settings('ECS_PASS')

logger = logging.getLogger(__name__)


class ECSResourceManager():
    """Class for managing objects related to an ECS cluster."""

    def __init__(self, resource, username=ECS_USER, password=ECS_PASS):
        self.resource = resource
        self.url = resource.resourceattribute_set.get(resource_attribute_type__name='url').value
        self._username = username
        self._password = password
        self.client = self.connect()


    def connect(self):
        client = Client(
                ECS_CLIENT_VERSION,
                username=self._username,
                password=self._password,
                token_endpoint=f'{self.url}:4443/login',
                ecs_endpoint=f'{self.url}:4443'
        )
        return client

    def generate_token(self, username, password):
        """Generate a token for ECS API access."""

    def create_allocation_bucket(self, lab_name, block_limit_tb):
        """Create a quota for a tenant."""
        bucket_name = f"lab-{lab_name}-bucket"
        block_limit_gb = block_limit_tb * 1024
        notification_limit_gb = int(block_limit_gb * 0.9)
        try:
            self.client.bucket.create(bucket_name, namespace=lab_name,
                replication_group='', filesystem_enabled=False,
               head_type=None, stale_allowed=None,
               metadata=None, encryption_enabled=False
            )
        except Exception as e:
            logger.exception("Error creating bucket %s: %s", bucket_name, str(e))
            raise
        self.client.bucket.set_quota(
                bucket_name,
                block_size=block_limit_gb,
                notification_size=notification_limit_gb,
        )

    def change_bucket_quota(self, bucket_name, new_block_size_tb, namespace_name=None):
        """Change a quota for a tenant."""
        # possibly use this in create_allocation_bucket as well
        new_block_size_gb = new_block_size_tb * 1024
        new_notification_size_gb = int(new_block_size_gb * 0.9)

        self.client.bucket.set_quota(
                bucket_name,
                namespace=namespace_name,
                block_size=new_block_size_gb,
                notification_size=new_notification_size_gb
        )

    def delete_allocation_bucket(self, bucket_name, namespace_name):
        """Delete a quota for a tenant."""
        self.client.bucket.delete(bucket_name, namespace=namespace_name)

    def update_resource_usage_data(self):
        """Get system usage data and update the corresponding resource records."""
        capacity_dict = self.client.capacity.get_cluster_capacity()
        allocated_tb = capacity_dict['totalProvisioned_gb'] / 1024
        free_tb = capacity_dict['totalFree_gb'] / 1024
        capacity_tb = allocated_tb + free_tb
        tb_dict = {'allocated_tb': allocated_tb, 'free_tb': free_tb, 'capacity_tb': capacity_tb}
        for k, v in tb_dict.items():
            logger.info("ECS Capacity %s: %.2f TB", k, v)
            attribute = self.resource.resourceattribute_set.get(resource_attribute_type__name=k)
            attribute.value = v
            attribute.save()
        return capacity_dict

    def update_bucket_allocation_usage_data(self, allocation, bucket_name, namespace_name):
        """Get bucket usage data and update the corresponding allocation records."""
        # for getting bucket stats:
        bucket_stats = self.client.billing.get_bucket_billing_info(
                bucket_name, namespace_name, sizeunit='KB')
        total_size_tb = bucket_stats['total_size'] / (1024 * 1024 * 1024)
        total_size_bytes = bucket_stats['total_size'] * 1024
        # update usage in bytes
        quota_bytes_attr = allocation.allocationattribute_set.get(
                allocation_attribute_type__name='Quota_In_Bytes')
        quota_bytes_attr.usage = total_size_bytes
        quota_bytes_attr.save()
        # update usage in TB
        quota_tb_attr = allocation.allocationattribute_set.get(
                allocation_attribute_type__name='Storage Quota (TB)'
        )
        quota_tb_attr.usage = total_size_tb
        quota_tb_attr.save()
