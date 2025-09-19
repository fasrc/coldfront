"""Command to sync ColdFront cluster allocation data with Slurm cluster data via Slurm REST API."""

import logging
import sys

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import Q

from coldfront.core.resource.models import Resource, ResourceAttribute
from coldfront.core.utils.common import import_from_settings
from coldfront.plugins.slurmrest.utils import (
        SlurmError,
        SLURM_CLUSTER_ATTRIBUTE_NAME,
        SlurmApiConnection,
)
SLURM_IGNORE_USERS = import_from_settings('SLURM_IGNORE_USERS', [])
SLURM_IGNORE_ACCOUNTS = import_from_settings('SLURM_IGNORE_ACCOUNTS', [])
SLURM_IGNORE_CLUSTERS = import_from_settings('SLURM_IGNORE_CLUSTERS', [])
SLURM_NOOP = import_from_settings('SLURM_NOOP', False)

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
                Q(resourceattribute__resourceattributetype__name=SLURM_CLUSTER_ATTRIBUTE_NAME) & 
                Q(resourceattribute__value=options.get('cluster'))
            )
        else:
            query = Q(
                Q(resourceattribute__resourceattributetype__name=SLURM_CLUSTER_ATTRIBUTE_NAME) &
                ~Q(resourceattribute__value__in=SLURM_IGNORE_CLUSTERS)
            )

        clusters = Resource.objects.filter(query).distinct()
        if not clusters:
            logger.info("No clusters found to sync")
            return
        # Process each cluster
        for cluster in clusters:
            cluster_name = cluster.get_attribute(SLURM_CLUSTER_ATTRIBUTE_NAME).value

            logger.info("Processing cluster %s (%s)", cluster.name, cluster_name)

            try:
                slurm_cluster = SlurmApiConnection(cluster_name)
            except SlurmError as e:
                logger.error("Failed to get Slurm data for cluster %s: %s", cluster.name, e)
                continue
            # get cluster data:
            # accounts/associations
            accounts = slurm_cluster.get_accounts()
            # partitions
            partitions = slurm_cluster.get_partitions()


