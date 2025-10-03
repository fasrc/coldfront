"""Command to sync ColdFront cluster allocation data with Slurm cluster data via Slurm REST API."""

import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import Q

from coldfront.core.allocation.models import (
    AllocationUserAttributeType,
    AllocationAttributeType,
    AllocationStatusChoice,
    AllocationUserStatusChoice
)
from coldfront.core.allocation.utils import get_or_create_allocation
from coldfront.core.project.models import Project
from coldfront.core.resource.models import Resource
from coldfront.core.utils.common import import_from_settings
from coldfront.plugins.slurmrest.utils import (
        SlurmError,
        SlurmApiConnection,
        calculate_fairshare_factor,
)

SLURMREST_CLUSTER_ATTRIBUTE_NAME = import_from_settings('SLURMREST_CLUSTER_ATTRIBUTE_NAME', 'slurm_cluster')
SLURM_IGNORE_USERS = import_from_settings('SLURMREST_IGNORE_USERS', [])
SLURM_IGNORE_ACCOUNTS = import_from_settings('SLURMREST_IGNORE_ACCOUNTS', [])
SLURM_IGNORE_CLUSTERS = import_from_settings('SLURMREST_IGNORE_CLUSTERS', [])
NOOP = import_from_settings('SLURMREST_NOOP', False)
SLURM_SPECS_ATTRIBUTE_NAME = import_from_settings('SLURMREST_SPECS_ATTRIBUTE_NAME', 'slurm_specs')

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = '''Sync ColdFront cluster allocation data with Slurm cluster data via Slurm REST API.
    '''
    noop = NOOP

    def add_arguments(self, parser):
        parser.add_argument('-n', '--noop',
            help='No operation mode: do not make any changes')
        parser.add_argument('-c', '--cluster',
                            help='select a specific cluster to check')

    def handle(self, *args, **options):
        if options.get('noop'):
            self.noop = True
            # Get clusters to process. If a specific cluster is given, filter by that.
            # Otherwise, get all clusters not on the SLURM_IGNORE_CLUSTERS list.
        if options.get('cluster'):
            additional_query = Q(resourceattribute__value=options.get('cluster'))
        else:
            additional_query = Q(~Q(resourceattribute__value__in=SLURM_IGNORE_CLUSTERS))
        clusters = Resource.objects.filter(Q(
            Q(resourceattribute__resource_attribute_type__name=SLURMREST_CLUSTER_ATTRIBUTE_NAME)
            & additional_query
        )).filter(resourceattribute__value='API').distinct()
        if not clusters:
            logger.info("No clusters found to sync")
            return
        # Process each cluster
        allocationuser_active_status = AllocationUserStatusChoice.objects.get(name="Active")
        allocation_inactive_status = AllocationStatusChoice.objects.get(name='Inactive')

        slurm_acct_name_attr_type = AllocationAttributeType.objects.get(
            name='slurm_account_name')
        cloud_acct_name_attr_type = AllocationAttributeType.objects.get(
            name='Cloud Account Name')
        hours_attr_type = AllocationAttributeType.objects.get(
            name='Core Usage (Hours)')
        fairshare_aattr_type = AllocationAttributeType.objects.get(name='FairShare')
        rawshares_aattr_type = AllocationAttributeType.objects.get(name='RawShares')
        normshares_aattr_type = AllocationAttributeType.objects.get(name='NormShares')
        rawusage_aattr_type = AllocationAttributeType.objects.get(name='RawUsage')
        effectvusage_aattr_type = AllocationAttributeType.objects.get(name='EffectvUsage')

        fairshare_auattr_type = AllocationUserAttributeType.objects.get(name='FairShare')
        rawshares_auattr_type = AllocationUserAttributeType.objects.get(name='RawShares')
        normshares_auattr_type = AllocationUserAttributeType.objects.get(name='NormShares')
        rawusage_auattr_type = AllocationUserAttributeType.objects.get(name='RawUsage')
        effectvusage_auattr_type = AllocationUserAttributeType.objects.get(name='EffectvUsage')

        for cluster in clusters:
            cluster_name = cluster.get_attribute(SLURMREST_CLUSTER_ATTRIBUTE_NAME)
            logger.info("Processing cluster %s (%s)", cluster.name, cluster_name)
            try:
                slurm_cluster = SlurmApiConnection(cluster_name)
            except SlurmError as e:
                logger.error("Failed to get Slurm data for cluster %s: %s", cluster.name, e)
                continue
            # get cluster data:
            # shares
            shares = slurm_cluster.get_shares()
            share_list = [
                share for share in shares['shares']['shares']
                if share['name'] not in SLURM_IGNORE_ACCOUNTS + SLURM_IGNORE_USERS
            ]
            calculate_fairshare = False
            if not [s for s in share_list if s['fairshare']['factor']['number'] != 0]:
                logger.warning("No valid fairshare values found for cluster %s, skipping update", cluster.name)
                calculate_fairshare = True
            # accounts/associations
            accounts = slurm_cluster.get_accounts()
            # remove accounts in SLURMREST_IGNORE_ACCOUNTS
            account_dicts = [
                acct for acct in accounts['accounts'] if acct['name'] not in SLURM_IGNORE_ACCOUNTS
            ]
            # for each account:
            cluster_resource = Resource.objects.get(name=cluster.name)
            for account in account_dicts:
                try:
                    project = Project.objects.get(title=account['name'])
                except Project.DoesNotExist:
                    logger.error(
                        "Project %s not in ColdFront, cannot create record for cluster %s share",
                        account['name'], cluster_name
                    )
                    continue
                # get or create related ColdFront allocation
                allocation, _ = get_or_create_allocation(project, cluster_resource)
                allocation.allocationattribute_set.get_or_create(
                    allocation_attribute_type=slurm_acct_name_attr_type,
                    defaults={'value': account['name']}
                )
                allocation.allocationattribute_set.get_or_create(
                    allocation_attribute_type=cloud_acct_name_attr_type,
                    defaults={'value': account['name']}
                )
                allocation.allocationattribute_set.get_or_create(
                    allocation_attribute_type=hours_attr_type,
                    defaults={'value': 0}
                )

                # add/update slurm specs
                group_share = next(
                    share for share in share_list if share['name'] == account['name']
                )
                normshares = group_share['shares_normalized']['number']
                effective_usage = group_share['effective_usage']['number']
                if calculate_fairshare:
                    fairshare_factor = calculate_fairshare_factor(
                        normshares, group_share['shares']['number']
                    )
                else:
                    fairshare_factor = group_share['fairshare']['factor']['number']
                spec_mapping = [
                    {'attrtype': rawshares_aattr_type, 'value': group_share['shares']['number']},
                    {'attrtype': normshares_aattr_type, 'value': round(normshares, 6)},
                    {'attrtype': rawusage_aattr_type, 'value': group_share['usage']},
                    {'attrtype': fairshare_aattr_type, 'value': round(fairshare_factor, 6)},
                    {'attrtype': effectvusage_aattr_type, 'value': round(effective_usage, 6)},
                        ]

                for spec_pair in spec_mapping:
                    alloc_attr, created = allocation.allocationattribute_set.update_or_create(
                        allocation_attribute_type=spec_pair['attrtype'],
                        defaults={'value': spec_pair['value']}
                    )

                # make list of users and update according allocation
                account_users = [assoc['user'] for assoc in account['associations']]
                allocation_users = allocation.allocationuser_set.all().values_list(
                    'user__username', flat=True
                )
                # add missing users
                user_shares = [
                    share for share in share_list if share['parent'] == account['name']
                ]
                for user_name in account_users:
                    if user_name in SLURM_IGNORE_USERS:
                        continue
                    if user_name not in allocation_users:
                        try:
                            user = get_user_model().objects.get(username=user_name)
                        except get_user_model().DoesNotExist:
                            logger.error(
                                "User %s not found in ColdFront, cannot add to %s allocation for project %s",
                                user_name, cluster.name, account['name']
                            )
                            continue
                        if not self.noop:
                            alloc_user = allocation.allocationuser_set.create(
                                user=user, status=allocationuser_active_status
                            )
                        logger.info(
                            "Added user %s to %s allocation for project %s",
                            user_name, cluster.name, account['name']
                        )
                    else:
                        # ensure the user is active in the allocation
                        alloc_user = allocation.allocationuser_set.get(user__username=user_name)
                        if not alloc_user.status == allocationuser_active_status:
                            if not self.noop:
                                alloc_user.status = allocationuser_active_status
                                alloc_user.save()
                            logger.info(
                                "Re-activated user %s in %s allocation for project %s",
                                user_name, cluster.name, account['name']
                            )
                    alloc_user = allocation.allocationuser_set.get(user__username=user_name)
                    user_share = next(
                        (share for share in user_shares if share['name'] == user_name), None
                    )
                    if not user_share:
                        logger.warning(
                            "No share data found for user %s in account %s on cluster %s",
                            user_name, account['name'], cluster.name
                        )
                        continue
                    normshares = user_share['shares_normalized']['number']
                    effective_usage = user_share['effective_usage']['number']
                    rawshares = user_share['shares']['number']
                    if rawshares > 200000:
                        rawshares = 'parent'
                    if calculate_fairshare:
                        if rawshares == 'parent':
                            rawshares_for_factor = group_share['shares']['number']
                        else:
                            rawshares_for_factor = rawshares
                        fairshare_factor = calculate_fairshare_factor(
                            normshares, rawshares_for_factor
                        )
                    else:
                        fairshare_factor = user_share['fairshare']['factor']['number']
                    spec_mapping = [
                        {'attrtype': rawshares_auattr_type, 'value': rawshares},
                        {'attrtype': normshares_auattr_type, 'value': round(normshares, 6)},
                        {'attrtype': rawusage_auattr_type, 'value': user_share['usage']},
                        {'attrtype': fairshare_auattr_type, 'value': round(fairshare_factor, 6)},
                        {'attrtype': effectvusage_auattr_type, 'value': round(effective_usage, 6)},
                    ]
                    for spec_pair in spec_mapping:
                        alloc_user_attr, created = alloc_user.allocationuserattribute_set.update_or_create(
                            allocationuser_attribute_type=spec_pair['attrtype'],
                            defaults={'value': spec_pair['value']}
                        )

            # partitions
            partitions = slurm_cluster.get_partitions()
            print(partitions)
            partition_names = [part['name'] for part in partitions['partitions']]
            # update allocation attributes for partitions



