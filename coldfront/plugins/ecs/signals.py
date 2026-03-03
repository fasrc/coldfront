import logging

from django.dispatch import receiver
from coldfront.core.allocation.signals import (
    allocation_autocreate,
    allocation_autoupdate,
)
from coldfront.plugins.ecs.utils import ECSResourceManager

logger = logging.getLogger(__name__)

@receiver(allocation_autocreate)
def activate_allocation(sender, **kwargs):
    approval_form_data = kwargs['approval_form_data']
    allocation_obj = kwargs['allocation_obj']
    resource = kwargs['resource']

    automation_specifications = approval_form_data.get('automation_specifications')
    automation_kwargs = {k:True for k in automation_specifications}

    if 'ecs' in resource.name:
        try:
            ecs_manager = ECSResourceManager(resource)
            block_limit_tb = allocation_obj.size_tb
            ecs_manager.create_allocation_bucket(allocation_obj.lab.name, block_limit_tb)
        except Exception as e:
            logger.exception(
                "error creating ecs allocation. allocation_pk=%s,error=%s",
                allocation_obj.pk, e,
                extra={'category': 'integration:ecs', 'status': 'error'},
            )
            raise
        return 'ecs'

@receiver(allocation_autoupdate)
def update_allocation(sender, **kwargs):
    allocation_obj = kwargs['allocation_obj']
    new_quota_value_tb = kwargs['new_quota_value']
    resource = allocation_obj.resources.first()

    if 'ecs' in resource.name:
        try:
            ecs_manager = ECSResourceManager(resource)
            ecs_manager.change_bucket_quota(
                bucket_name=f"lab-{allocation_obj.lab.name}-bucket",
                new_block_size_tb=new_quota_value_tb
            )
            logger.info(
                "Auto-updated allocation %s bucket quota from %s to %s",
                allocation_obj, allocation_obj.size, new_quota_value_tb,
                extra={'category': 'integration:ecs', 'status': 'success'},
            )
        except Exception as e:
            logger.exception(
                "error updating bucket allocation quota. allocation_pk=%s,error=%s",
                allocation_obj.pk, e,
                extra={'category': 'integration:ecs', 'status': 'error'},
            )
            raise
        return 'ecs'
