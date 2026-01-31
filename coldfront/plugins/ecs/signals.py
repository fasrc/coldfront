import logging

from django.dispatch import receiver
from coldfront.core.allocation.signals import allocation_autocreate
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
            err = ("An error was encountered while auto-creating the "
                "allocation. Please contact Coldfront administration "
                f"and/or manually create the allocation: {e}")
            logger.error(err)
            raise ValueError(err)
        return 'ecs'
