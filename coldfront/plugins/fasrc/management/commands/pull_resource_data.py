import logging
from django.core.management.base import BaseCommand

from coldfront.core.resource.models import Resource
from coldfront.core.resource.signals import update_volume_information
from sftocf.signals import starfish_update_volume_information


logger = logging.getLogger(__name__)

class Command(BaseCommand):
    """Pull storage capacity/usage data and save it to ResourceAttribute objects.

    Dispatches update_volume_information for every Storage resource; each
    storage-backend plugin living in this same coldfront repo (e.g. isilon;
    see coldfront.plugins.isilon.signals) owns a receiver that updates the
    resources it recognizes and ignores the rest, so this command doesn't need
    to import those directly. A separate signal gets sent to the sftocf plugin.
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
            starfish_update_volume_information.send(
                sender=self.__class__, resource=resource, source=options['source']
            )
