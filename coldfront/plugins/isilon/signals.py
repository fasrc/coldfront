import logging

from django.dispatch import receiver
from coldfront.core.allocation.signals import allocation_autocreate
from coldfront.plugins.isilon.utils import create_isilon_allocation_quota

logger = logging.getLogger(__name__)

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
            err = ("An error was encountered while auto-creating the "
                "allocation. Please contact Coldfront administration "
                f"and/or manually create the allocation: {e}")
            logger.error(err)
            raise ValueError(err)
        return 'isilon'
