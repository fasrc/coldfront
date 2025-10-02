from django.dispatch import receiver

from coldfront.core.allocation.models import AllocationUser, AllocationUserAttributeType
from coldfront.core.allocation.signals import (
    allocation_user_attribute_edit,
    allocation_user_remove_on_slurm,
    allocation_user_add_on_slurm,
    allocation_activate_user,
    allocation_raw_share_edit
)
from coldfront.plugins.slurmrest.utils import SlurmApiConnection, SlurmError


@receiver(allocation_user_attribute_edit)
def allocation_user_attribute_edit_handler(sender, **kwargs):
    """Update Slurm user's raw share when the AllocationUser's raw share attribute is edited."""
    slurm_cluster = kwargs.get('cluster')
    if not slurm_cluster or slurm_cluster.get_attribute('slurm_integration') != 'API':
        return
    raise NotImplementedError("Editing AllocationUser attributes is not yet implemented for Slurm REST API integration.")
    api = SlurmApiConnection(slurm_cluster.get_attribute('slurm_cluster'))
    api.update_user(kwargs['user'], kwargs['account'], {'RawShares': str(kwargs['raw_share'])})


@receiver(allocation_user_add_on_slurm)
def allocation_add_user_handler(sender, **kwargs):
    slurm_cluster = kwargs.get('cluster')
    if not slurm_cluster or slurm_cluster.get_attribute('slurm_integration') != 'API':
        return
    api = SlurmApiConnection(slurm_cluster.get_attribute('slurm_cluster'))
    api.add_assoc(kwargs['username'], kwargs['account'])


@receiver(allocation_user_remove_on_slurm)
def allocation_user_deactivate_handler(sender, **kwargs):
    """Remove Slurm association when the AllocationUser is removed."""
    slurm_cluster = kwargs.get('cluster')
    if not slurm_cluster or slurm_cluster.get_attribute('slurm_integration') != 'API':
        return
    raise NotImplementedError("Removing AllocationUser is not yet implemented for Slurm REST API integration.")
    api = SlurmApiConnection(slurm_cluster.get_attribute('slurm_cluster'))
    api.remove_assoc(user_name=kwargs['username'], account_name=kwargs['account'])


@receiver(allocation_raw_share_edit)
def allocation_raw_share_edit_handler(sender, **kwargs):
    """Update Slurm account's raw share when the Allocation's raw share attribute is edited."""
    slurm_cluster = kwargs.get('cluster')
    if not slurm_cluster or slurm_cluster.get_attribute('slurm_integration') != 'API':
        return
    raise NotImplementedError("Editing Allocation attributes is not yet implemented for Slurm REST API integration.")
    api = SlurmApiConnection(slurm_cluster.get_attribute('slurm_cluster'))
    slurmrest_update_account_raw_share(kwargs['account'], str(kwargs['raw_share']))


@receiver(allocation_activate_user)
def allocation_activate_user_handler(sender, **kwargs):
    """import slurm data about user to coldfront when user is activated"""
    slurm_cluster = kwargs.get('cluster')
    if not slurm_cluster or slurm_cluster.get_attribute('slurm_integration') != 'API':
        return
    api = SlurmApiConnection(slurm_cluster.get_attribute('slurm_cluster'))
    allocationuser = AllocationUser.objects.get(pk=kwargs['allocation_user_pk'])
    username = allocationuser.user.username
    project_title = allocationuser.allocation.project.title

    share_data = api.get_shares()
    user_data = next(
        e for e in share_data['shares']['shares']
        if e['name'] == username and e['parent'] == project_title
    )
    if not user_data:
        raise SlurmError(f"Unable to find Slurm user {username} for account {project_title} on cluster {slurm_cluster.name}")
    spec_values = {
        'RawShares': user_data['shares']['number'],
        'NormShares': user_data['shares_normalized']['number'],
        'RawUsage': user_data['usage'],
        'FairShare': user_data['effective_usage']['number'],
    }
    for spec, value in spec_values.items():
        allocationuser.allocationuserattribute_set.update_or_create(
            allocationuser_attribute_type=AllocationUserAttributeType.objects.get(name=spec),
            defaults={'value': value}
        )
