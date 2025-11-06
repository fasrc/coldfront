from django.dispatch import receiver

from coldfront.core.allocation.models import AllocationUser, AllocationUserAttributeType
from coldfront.core.allocation.signals import (
    allocation_user_attribute_edit,
    allocation_user_remove_on_slurm,
    allocation_user_add_on_slurm,
    allocation_activate_user,
    allocation_raw_share_edit
)
from coldfront.core.resource.signals import resource_clicluster_table_data_request
from django.db.models import Q, Value, Subquery, OuterRef, IntegerField, FloatField
from django.db.models.functions import Substr, StrIndex, Coalesce, Cast, Length, Round
from coldfront.core.resource.models import Resource
from coldfront.core.allocation.models import AllocationAttribute, AllocationAttributeType
from coldfront.plugins.slurm.utils import (
    slurm_update_raw_share,
    slurm_remove_assoc,
    slurm_add_assoc,
    slurm_get_user_info,
    slurm_update_account_raw_share
)


@receiver(allocation_user_attribute_edit)
def allocation_user_attribute_edit_handler(sender, **kwargs):
    slurm_cluster = Resource.objects.get(
        Q(resourceattribute__resource_attribute_type__name='slurm_cluster') &
        Q(resourceattribute__value=kwargs.get('cluster'))
    )
    if not slurm_cluster or slurm_cluster.get_attribute('slurm_integration') != 'CLI':
        return
    slurm_update_raw_share(kwargs['user'], kwargs['account'], str(kwargs['raw_share']))


@receiver(allocation_user_remove_on_slurm)
def allocation_user_deactivate_handler(sender, **kwargs):
    slurm_cluster = Resource.objects.get(
        Q(resourceattribute__resource_attribute_type__name='slurm_cluster') &
        Q(resourceattribute__value=kwargs.get('cluster'))
    )
    if not slurm_cluster or slurm_cluster.get_attribute('slurm_integration') != 'CLI':
        return
    slurm_remove_assoc(kwargs['username'], kwargs['account'])


@receiver(allocation_raw_share_edit)
def allocation_raw_share_edit_handler(sender, **kwargs):
    slurm_cluster = Resource.objects.get(
        Q(resourceattribute__resource_attribute_type__name='slurm_cluster') &
        Q(resourceattribute__value=kwargs.get('cluster'))
    )
    if not slurm_cluster or slurm_cluster.get_attribute('slurm_integration') != 'CLI':
        return
    slurm_update_account_raw_share(kwargs['account'], str(kwargs['raw_share']))


@receiver(allocation_user_add_on_slurm)
def allocation_add_user_handler(sender, **kwargs):
    slurm_cluster = Resource.objects.get(
        Q(resourceattribute__resource_attribute_type__name='slurm_cluster') &
        Q(resourceattribute__value=kwargs.get('cluster'))
    )
    if not slurm_cluster or slurm_cluster.get_attribute('slurm_integration') != 'CLI':
        return
    slurm_add_assoc(kwargs['username'], kwargs['cluster'], kwargs['account'], specs=['Fairshare=parent'])

@receiver(allocation_activate_user)
def allocation_activate_user_handler(sender, **kwargs):
    """import slurm data about user to coldfront when user is activated"""
    allocationuser = AllocationUser.objects.get(pk=kwargs['allocation_user_pk'])
    username = allocationuser.user.username
    project_title = allocationuser.allocation.project.title
    slurm_cluster = allocationuser.allocation.get_parent_resource
    if slurm_cluster.get_attribute('slurm_integration') != 'CLI':
        return
    slurm_stats = slurm_get_user_info(username, project_title)
    keys = slurm_stats[0].split('|')
    values = next(i for i in slurm_stats if username in i and project_title in i).split('|')
    stats = dict(zip(keys, values))
    # Extract only the fields we want in the order specified
    wanted_fields = ['RawShares', 'NormShares', 'RawUsage', 'FairShare']
    result = ','.join(f"{field}={stats[field]}" for field in wanted_fields)
    # set the value of the allocationuser attribute to the result
    slurm_specs_allocuser_attrtype = AllocationUserAttributeType.objects.get(name='slurm_specs')
    allocationuser.allocationuserattribute_set.update_or_create(
        allocationuser_attribute_type=slurm_specs_allocuser_attrtype,
        defaults={"value": result}
    )

@receiver(resource_clicluster_table_data_request)
def generate_cluster_resource_allocation_table_data(sender, **kwargs):
    """Generate allocation table data for a cluster resource.
    This function is called when generating the allocation table data for a cluster resource.
    It adds Slurm-specific data to the allocation table.
    """
    allocations = kwargs['allocations']
    total_hours = kwargs['total_hours']
    slurm_specs_type = AllocationAttributeType.objects.get(name='slurm_specs')
    usage_type = AllocationAttributeType.objects.get(name='Core Usage (Hours)')
    effectv_type = AllocationAttributeType.objects.get(name='EffectvUsage')

    allocations = (
        allocations.annotate(
            # For slurm_specs parsing
            specs_value=Subquery(
                AllocationAttribute.objects.filter(
                    allocation_id=OuterRef('id'),
                    allocation_attribute_type=slurm_specs_type
                )
                .values('value')[:1]
            ),
            rawshares=Substr(
                'specs_value',
                StrIndex('specs_value', Value('RawShares=')) + 10,
                Cast(StrIndex(
                    Substr(
                        'specs_value',
                        StrIndex('specs_value', Value('RawShares=')) + 10
                    ),
                    Value(',')
                ) - 1, IntegerField())
            ),
            normshares=Substr(
                'specs_value',
                StrIndex('specs_value', Value('NormShares=')) + 11,
                Cast(StrIndex(
                    Substr(
                        'specs_value',
                        StrIndex('specs_value', Value('NormShares=')) + 11
                    ),
                    Value(',')
                ) - 1, IntegerField())
            ),
            fairshare=Substr(
                'specs_value',
                StrIndex('specs_value', Value('FairShare=')) + 10,
                Length('specs_value')
            ),
            usage=Round(Cast(
                Coalesce(
                    Subquery(
                        AllocationAttribute.objects.filter(
                            allocation_id=OuterRef('id'),
                            allocation_attribute_type=usage_type
                        ).values('value')[:1]
                    ), Value('0')
                ), FloatField())
            , 1),
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
                ),
                Value('0')
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
