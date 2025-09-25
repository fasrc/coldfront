"""Command to sync ColdFront cluster allocation data with Slurm cluster data via Slurm REST API."""

import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import Q

from coldfront.core.allocation.models import (
    Allocation,
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
)
SLURMREST_CLUSTER_ATTRIBUTE_NAME = import_from_settings('SLURMREST_CLUSTER_ATTRIBUTE_NAME', 'slurm_cluster')
SLURM_IGNORE_USERS = import_from_settings('SLURMREST_IGNORE_USERS', [])
SLURM_IGNORE_ACCOUNTS = import_from_settings('SLURMREST_IGNORE_ACCOUNTS', [])
SLURM_IGNORE_CLUSTERS = import_from_settings('SLURMREST_IGNORE_CLUSTERS', [])
SLURM_NOOP = import_from_settings('SLURMREST_NOOP', False)
SLURM_SPECS_ATTRIBUTE_NAME = import_from_settings('SLURMREST_SPECS_ATTRIBUTE_NAME', 'slurm_specs')

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = '''Sync ColdFront cluster allocation data with Slurm cluster data via Slurm REST API.
    '''
    noop = SLURM_NOOP

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
            query = Q(
                Q(resourceattribute__resourceattributetype__name=SLURMREST_CLUSTER_ATTRIBUTE_NAME)
                & Q(resourceattribute__value=options.get('cluster'))
            )
        else:
            query = Q(
                Q(resourceattribute__resource_attribute_type__name=SLURMREST_CLUSTER_ATTRIBUTE_NAME)
                & ~Q(resourceattribute__value__in=SLURM_IGNORE_CLUSTERS)
            )

        clusters = Resource.objects.filter(query).distinct()
        if not clusters:
            logger.info("No clusters found to sync")
            return
        # Process each cluster
        allocationuser_active_status = AllocationUserStatusChoice.objects.get(name="Active")
        allocation_active_status = AllocationStatusChoice.objects.get(name="Active")
        slurm_specs_attribute_type = AllocationAttributeType.objects.get(name=SLURM_SPECS_ATTRIBUTE_NAME)
        for cluster in clusters:
            cluster_name = cluster.get_attribute(SLURMREST_CLUSTER_ATTRIBUTE_NAME)
            logger.info("Processing cluster %s (%s)", cluster.name, cluster_name)
            try:
                slurm_cluster = SlurmApiConnection(cluster_name)
            except SlurmError as e:
                logger.error("Failed to get Slurm data for cluster %s: %s", cluster.name, e)
                continue
            # get cluster data:
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
                    project = Project.objects.filter(title=account['name']).first()
                except Project.DoesNotExist:
                    logger.error(
                        "Project %s not in ColdFront, cannot create record for cluster %s share",
                        account['name'], cluster_name
                    )
                    continue
                # get or create related ColdFront allocation
                allocation = get_or_create_allocation(project, cluster_resource)
                # make list of users and update according allocation
                account_users = [assoc['user'] for assoc in account['associations']]
                allocation_users = allocation.allocationuser_set.all().values_list(
                    'user__username', flat=True
                )
                # add slurm specs
                # add missing users
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
                            allocation.allocationuser_set.create(
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

            # partitions
            partitions = slurm_cluster.get_partitions()
            partition_names = [part['name'] for part in partitions['partitions']]
            # update allocation attributes for partitions



