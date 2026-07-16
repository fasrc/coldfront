import logging

from django.core.management.base import BaseCommand

from coldfront.core.resource.models import Resource
from coldfront.plugins.vast.utils import sync_vast_resource_allocations

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Sync VAST userquotas into ColdFront allocations
    """
    help = 'Sync VAST userquotas into ColdFront allocations'

    def add_arguments(self, parser):
        parser.add_argument(
            '-r', '--resource', help='Sync only the named vast Storage resource'
        )

    def handle(self, *args, **options):
        vast_resources = Resource.objects.filter(
            resourceattribute__value='vast',
            is_available=True,
        )
        if options.get('resource'):
            vast_resources = vast_resources.filter(name=options['resource'])

        if not vast_resources.exists():
            logger.warning('No active vast resources found matching %s', options.get('resource'))
            return

        all_missing_projects = []
        for resource in vast_resources:
            try:
                report = sync_vast_resource_allocations(resource)
            except Exception as e:
                logger.exception('Could not sync allocations for resource %s: %s', resource.name, e)
                continue
            all_missing_projects.extend(report['missing_projects'])
            logger.info('vast allocation sync report for %s: %s', resource.name, report)

        if all_missing_projects:
            logger.warning(
                'sync_vast_allocations: no matching ColdFront Project found for groups: %s',
                sorted(set(all_missing_projects)),
            )
