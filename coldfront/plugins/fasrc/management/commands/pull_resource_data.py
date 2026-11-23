import logging
from django.core.management.base import BaseCommand

from coldfront.core.resource.models import Resource
from coldfront.core.resource.signals import update_volume_information


logger = logging.getLogger(__name__)

class Command(BaseCommand):
    """Pull storage capacity/usage data and save it to ResourceAttribute objects.

    Dispatches update_volume_information for every Storage resource; each
    storage-backend plugin owns a receiver that updates the resources it
    recognizes and ignores the rest (see coldfront.plugins.isilon.signals and
    sftocf.receivers), so this command never needs to import a backend plugin
    directly.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            '--source',
            dest='source',
            default='redash',
            help='source to pull data from: "rest_api" or "redash" (default: "redash")',
        )

    def handle(self, *args, **options):
        resources = Resource.objects.filter(resource_type__name='Storage', is_available=True)
        for resource in resources:
            update_volume_information.send(
                sender=self.__class__, resource=resource, source=options['source']
            )
