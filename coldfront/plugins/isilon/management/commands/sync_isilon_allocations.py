import logging

from django.core.management.base import BaseCommand

from coldfront.core.resource.models import Resource
from coldfront.plugins.isilon.utils import print_log_error, sync_isilon_resource_allocations

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Sync Isilon/PowerScale directory smartquotas into ColdFront allocations
    """
    help = 'Sync Isilon/PowerScale directory smartquotas into ColdFront allocations'

    def add_arguments(self, parser):
        parser.add_argument(
            '-r', '--resource', help='Sync only the named isilon/powerscale Storage resource'
        )

    def handle(self, *args, **options):
        isilon_resources = Resource.objects.filter(
            resourceattribute__value__in=('isilon', 'powerscale'),
            is_available=True,
        )
        if options.get('resource'):
            isilon_resources = isilon_resources.filter(name=options['resource'])

        if not isilon_resources.exists():
            logger.warning('No active isilon/powerscale resources found matching %s', options.get('resource'))
            return

        all_missing_projects = []
        for resource in isilon_resources:
            try:
                report = sync_isilon_resource_allocations(resource)
            except Exception as e:
                print_log_error(e, f'Could not sync allocations for resource {resource.name}')
                continue
            all_missing_projects.extend(report['missing_projects'])
            logger.info('isilon allocation sync report for %s: %s', resource.name, report)

        if all_missing_projects:
            logger.warning(
                'sync_isilon_allocations: no matching ColdFront Project found for groups: %s',
                sorted(set(all_missing_projects)),
            )
