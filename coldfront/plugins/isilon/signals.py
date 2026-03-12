import logging

from django.dispatch import receiver
from coldfront.core.allocation.signals import (
        allocation_autocreate,
        allocation_autoupdate,
)
from coldfront.core.resource.models import ResourceAttributeType
from coldfront.core.resource.signals import update_volume_information
from coldfront.plugins.isilon.utils import (
    IsilonConnection,
    create_isilon_allocation_quota,
    update_isilon_allocation_quota,
)

logger = logging.getLogger(__name__)

@receiver(update_volume_information)
def update_isilon_volume_information(sender, **kwargs):

    resource = kwargs['resource']
    if 'isilon' in resource.name:
        resource_name = resource.name.split('/')[0]
        isilon_api = IsilonConnection(resource_name)
        isilon_capacity_tb = isilon_api.to_tb(isilon_api.total_space)
        isilon_free_tb = isilon_api.to_tb(isilon_api.unused_space)
        isilon_allocated_tb = isilon_api.to_tb(isilon_api.allocated_space)
        isilon_used_tb = isilon_api.to_tb(isilon_api.used_space)
        attr_pairs = {
            'capacity_tb': isilon_capacity_tb,
            'allocated_tb': isilon_allocated_tb,
            'free_tb': isilon_free_tb,
            'used_tb': isilon_used_tb,
        }
        for attr_name, attr_val in attr_pairs.items():
            if attr_val:
                attr_type_obj = ResourceAttributeType.objects.get(name=attr_name)
                resource.resourceattribute_set.update_or_create(
                    resource_attribute_type=attr_type_obj,
                    defaults={'value': attr_val}
                )

@receiver(allocation_autocreate)
def activate_allocation(sender, **kwargs):

    approval_form_data = kwargs['approval_form_data']
    allocation_obj = kwargs['allocation_obj']
    resource = kwargs['resource']

    automation_specifications = approval_form_data.get('automation_specifications')
    automation_kwargs = {k:True for k in automation_specifications}

    if 'isilon' in resource.name:
        try:
            option_exceptions = create_isilon_allocation_quota(
                allocation_obj, resource, **automation_kwargs
            )
            if option_exceptions:
                err = f'some options failed to be created for new allocation {allocation_obj} ({allocation_obj.pk}): {option_exceptions}'
                logger.error(err)
                raise ValueError(err)
        except Exception as e:
            logger.exception("error encountered trying to create isilon allocation: %s", e)
            raise
        return 'isilon'

@receiver(allocation_autoupdate)
def update_allocation_quota(sender, **kwargs):
    allocation_obj = kwargs['allocation_obj']
    new_quota_value = kwargs['new_quota_value']
    resource = allocation_obj.resources.first()
    if 'isilon' in resource.name:
        try:
            update_isilon_allocation_quota(allocation_obj, new_quota_value)
            logger.info(
                "Auto-updated allocation %s isilon quota from %s to %s",
                allocation_obj, allocation_obj.size, new_quota_value,
                extra={'category': 'integration:isilon', 'status': 'success'},
            )
        except Exception as e:
            logger.exception(
                'error encountered trying to update allocation %s quota: %s',
                allocation_obj.pk, e,
                extra={'category': 'integration:isilon', 'status': 'error'},
            )
            raise
        return 'isilon'
