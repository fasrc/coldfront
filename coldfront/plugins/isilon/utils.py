import logging

import isilon_sdk.v9_3_0
from isilon_sdk.v9_3_0.rest import ApiException

from coldfront.core.allocation.models import Allocation, AllocationAttributeType
from coldfront.core.resource.models import Resource
from coldfront.core.utils.common import import_from_settings

logger = logging.getLogger(__name__)

def connect(cluster_name):
    configuration = isilon_sdk.v9_3_0.Configuration()
    configuration.host = f'http://{cluster_name}01.rc.fas.harvard.edu:8080'
    configuration.username = import_from_settings('ISILON_USER')
    configuration.password = import_from_settings('ISILON_PASS')
    configuration.verify_ssl = False
    api_client = isilon_sdk.v9_3_0.ApiClient(configuration)
    return api_client


def update_quota_and_usage(alloc, usage_attribute_type, value_list):
    usage_attribute, _ = alloc.allocation.allocationattribute_set.get_or_create(
        allocation_attribute_type=usage_attribute_type
    )
    usage_attribute.value = value_list[0]
    usage_attribute.save()
    usage = usage_attribute.allocationattributeusage
    usage.value = value_list[1]
    usage.save()
    return usage_attribute

def update_quotas_usages():
    """For all active tier1 allocations, update quota and usage
    1. run a query that collects all active tier1 allocations
    """
    quota_bytes_attributetype = AllocationAttributeType.objects.get(
        name='Quota_In_Bytes')
    quota_tbs_attributetype = AllocationAttributeType.objects.get(
        name='Storage Quota (TB)')
    # create isilon connections to all isilon clusters in coldfront
    isilon_resources = Resource.objects.filter(name__contains='tier1')
    isilon_clusters = {}
    for resource in isilon_resources:
        resource_name = resource.name.split('/')[0]
        # try connecting to the cluster. If it fails, display an error and
        # replace the resource with a dummy resource
        try:
            api_client = connect(resource_name)
            isilon_clusters[resource.name] = isilon_sdk.v9_3_0.QuotaApi(api_client)
        except Exception as e:
            message = f'Could not connect to {resource_name} - will not update quotas for allocations on this resource'
            logger.warning("%s Error: %s", message, e)
            print(f"{message} Error: {e}")
            # isilon_clusters[resource.name] = None

    isilon_allocations = Allocation.objects.filter(
        is_active=True,
        resource__in=isilon_clusters.keys(),
    )

    for allocation in isilon_allocations:
        # get the api instance for this allocation. If it doesn't exist, skip
        api_instance = isilon_clusters[allocation.resource.name]
        if not api_instance:
            continue
        try:
            api_response = api_instance.get_quota_quota(
                path=allocation.resource.path,
                recurse_path_children=True,
            )
        except ApiException as e:
            message = f'Exception when calling QuotaApi->list_quotas: {e}'
            print(message)
            logger.warning(message)
            continue
        # update the quota and usage for this allocation
        quota = api_response['thresholds']['hard']
        usage = api_response['usage']['fslogical']
        quota_tb = quota / 1024 / 1024 / 1024 / 1024
        usage_tb = usage / 1024 / 1024 / 1024 / 1024
        update_quota_and_usage(
            allocation, quota_bytes_attributetype, [quota, usage]
        )
        update_quota_and_usage(
            allocation, quota_tbs_attributetype, [quota_tb, usage_tb]
        )