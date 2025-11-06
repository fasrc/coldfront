from django.dispatch import receiver
from django.db.models import Q, Value, Subquery, OuterRef, IntegerField, FloatField
from django.db.models.functions import Coalesce, Cast, Round
from coldfront.core.resource.signals import resource_apicluster_table_data_request

from coldfront.core.allocation.models import (
    AllocationUser,
    AllocationUserAttributeType,
    AllocationAttribute,
    AllocationAttributeType
)
from coldfront.core.allocation.signals import (
    allocation_user_attribute_edit,
    allocation_user_remove_on_slurm,
    allocation_user_add_on_slurm,
    allocation_activate_user,
    allocation_raw_share_edit
)
from coldfront.core.resource.models import Resource
from coldfront.plugins.slurmrest.utils import (
    SlurmApiConnection, SlurmError, calculate_fairshare_factor
)


@receiver(allocation_user_attribute_edit)
def slurmrest_allocation_user_attribute_edit_handler(sender, **kwargs):
    """Update Slurm user's raw share when the AllocationUser's raw share attribute is edited."""
    slurm_cluster = Resource.objects.get(
        Q(resourceattribute__resource_attribute_type__name='slurm_cluster') &
        Q(resourceattribute__value=kwargs.get('cluster'))
    )
    if not slurm_cluster or slurm_cluster.get_attribute('slurm_integration') != 'API':
        return
    api = SlurmApiConnection(slurm_cluster.get_attribute('slurm_cluster'))
    api.post_assoc(kwargs['account'], kwargs['user'], {'shares_raw': str(kwargs['raw_share'])})


@receiver(allocation_user_add_on_slurm)
def slurmrest_allocation_add_user_handler(sender, **kwargs):
    slurm_cluster = Resource.objects.get(
        Q(resourceattribute__resource_attribute_type__name='slurm_cluster') &
        Q(resourceattribute__value=kwargs.get('cluster'))
    )
    if not slurm_cluster or slurm_cluster.get_attribute('slurm_integration') != 'API':
        return
    api = SlurmApiConnection(slurm_cluster.get_attribute('slurm_cluster'))
    api.add_assoc(kwargs['account'], kwargs['username'])


@receiver(allocation_user_remove_on_slurm)
def slurmrest_allocation_user_deactivate_handler(sender, **kwargs):
    """Remove Slurm association when the AllocationUser is removed."""
    slurm_cluster = Resource.objects.get(
        Q(resourceattribute__resource_attribute_type__name='slurm_cluster') &
        Q(resourceattribute__value=kwargs.get('cluster'))
    )
    if not slurm_cluster or slurm_cluster.get_attribute('slurm_integration') != 'API':
        return
    api = SlurmApiConnection(slurm_cluster.get_attribute('slurm_cluster'))
    api.remove_assoc(user_name=kwargs['username'], account_name=kwargs['account'])


@receiver(allocation_raw_share_edit)
def slurmrest_allocation_raw_share_edit_handler(sender, **kwargs):
    """Update Slurm account's raw share when the Allocation's raw share attribute is edited."""
    slurm_cluster = Resource.objects.get(
        Q(resourceattribute__resource_attribute_type__name='slurm_cluster') &
        Q(resourceattribute__value=kwargs.get('cluster'))
    )
    if not slurm_cluster or slurm_cluster.get_attribute('slurm_integration') != 'API':
        return
    api = SlurmApiConnection(slurm_cluster.get_attribute('slurm_cluster'))
    api.post_assoc(kwargs['account'], "", {'shares_raw': str(kwargs['raw_share'])})


@receiver(allocation_activate_user)
def slurmrest_allocation_activate_user_handler(sender, **kwargs):
    """import slurm data about user to coldfront when user is activated"""
    allocationuser = AllocationUser.objects.get(pk=kwargs['allocation_user_pk'])
    slurm_cluster = allocationuser.allocation.get_parent_resource
    if slurm_cluster.get_attribute('slurm_integration') != 'API':
        return
    api = SlurmApiConnection(slurm_cluster.get_attribute('slurm_cluster'))
    username = allocationuser.user.username
    project_title = allocationuser.allocation.project.title

    share_data = api.get_shares()
    user_data = next(
        (e for e in share_data['shares']['shares']
        if e['name'] == username and e['parent'] == project_title), None
    )
    if not user_data:
        raise SlurmError(f"Unable to find Slurm user {username} for account {project_title} on cluster {slurm_cluster.name}")
    normshares = user_data['shares_normalized']['number']
    effective_usage = user_data['effective_usage']['number']
    fairshare = calculate_fairshare_factor(normshares, effective_usage)
    spec_values = {
        'RawShares': user_data['shares']['number'],
        'NormShares': normshares,
        'RawUsage': user_data['usage'],
        'EffectvUsage': effective_usage,
        'FairShare': fairshare,
    }
    for spec, value in spec_values.items():
        allocationuser.allocationuserattribute_set.update_or_create(
            allocationuser_attribute_type=AllocationUserAttributeType.objects.get(name=spec),
            defaults={'value': value}
        )

@receiver(resource_apicluster_table_data_request)
def generate_cluster_resource_allocation_table_data(sender, **kwargs):
    """Generate allocation table data for a cluster resource.
    """
    allocations = kwargs['allocations']
    total_hours = kwargs['total_hours']
    # Get attribute type IDs
    rawshare_attribute_type = AllocationAttributeType.objects.get(name='RawShares')
    normshare_attribute_type = AllocationAttributeType.objects.get(name='NormShares')
    fairshare_attribute_type = AllocationAttributeType.objects.get(name='FairShare')
    usage_type = AllocationAttributeType.objects.get(name='Core Usage (Hours)')
    effectv_type = AllocationAttributeType.objects.get(name='EffectvUsage')

    allocations = (
        allocations.annotate(
            rawshares=Cast(Coalesce(
                Subquery(
                    AllocationAttribute.objects.filter(
                        allocation_id=OuterRef('id'),
                        allocation_attribute_type=rawshare_attribute_type
                    )
                    .values('value')[:1]
                ),
                Value('0')
            ), IntegerField()),
            normshares=Cast(Coalesce(
                Subquery(
                    AllocationAttribute.objects.filter(
                        allocation_id=OuterRef('id'),
                        allocation_attribute_type=normshare_attribute_type
                    )
                    .values('value')[:1]
                ),
                Value('0')
            ), FloatField()),
            fairshare=Cast(Coalesce(
                Subquery(
                    AllocationAttribute.objects.filter(
                        allocation_id=OuterRef('id'),
                        allocation_attribute_type=fairshare_attribute_type
                    )
                    .values('value')[:1]
                ),
                Value('0')
            ), FloatField()),
            usage=Round(Cast(
                Coalesce(
                    Subquery(
                        AllocationAttribute.objects.filter(
                            allocation_id=OuterRef('id'),
                            allocation_attribute_type=usage_type
                        )
                        .values('value')[:1]
                    ), Value('0')
                ), FloatField()
            ), 1),
            usage_pct=Round(
                100.0 * Cast(
                    Coalesce(
                        Subquery(
                            AllocationAttribute.objects.filter(
                                allocation_id=OuterRef('id'),
                                allocation_attribute_type=usage_type
                            )
                            .values('value')[:1]
                        ),
                        Value('0')
                    ), FloatField()
                ) / Cast(Value(total_hours), FloatField()
            ), 2),
            effectvusage=Cast(Coalesce(
                Subquery(
                    AllocationAttribute.objects.filter(
                        allocation_id=OuterRef('id'),
                        allocation_attribute_type=effectv_type
                    )
                    .values('value')[:1]
                ), Value('0')
            ), FloatField())
        )
        .order_by('id')
        .values(
            'id',
            'project_title',
            'user_count',
            'rawshares',
            'normshares',
            'fairshare',
            'usage',
            'usage_pct',
            'effectvusage'
        )
    )
    return allocations
