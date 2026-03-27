import logging
from django.core.management.base import BaseCommand

from coldfront.core.resource.models import Resource, ResourceAttributeType
from coldfront.core.resource.signals import update_volume_information
from sftocf.utils import StarFishServer, StarFishRedash


logger = logging.getLogger(__name__)

def update_resource_attr_types_from_dict(resource, res_attr_type_dict):
    for attr_name, attr_val in res_attr_type_dict.items():
        if attr_val:
            attr_type_obj = ResourceAttributeType.objects.get(name=attr_name)
            resource.resourceattribute_set.update_or_create(
                resource_attribute_type=attr_type_obj,
                defaults={'value': attr_val}
            )

class Command(BaseCommand):
    """Pull data from starfish and save to ResourceAttribute objects
    """

    def add_arguments(self, parser):
        parser.add_argument(
            '--source',
            dest='source',
            default='redash',
            help='source to pull data from: "rest_api" or "redash" (default: "redash")',
        )

    def handle(self, *args, **options):
        source = options['source']
        if source == 'rest_api':
            sf = StarFishServer()
            volumes = sf.get_volume_attributes()
            for vol in volumes:
                vol['capacity_tb'] = vol['total_capacity']/(1024**4)
                vol['free_tb'] = vol['free_space']/(1024**4)
                vol['used_tb'] = (vol['total_capacity'] - vol['free_space'])/(1024**4)
            volumes = [
                {
                    'name': vol['vol'],
                    'attrs': {
                        'capacity_tb': vol['capacity_tb'],
                        'free_tb': vol['free_tb'],
                        'file_count': vol['number_of_files'],
                        'used_tb': vol['used_tb'],
                    }
                }
                for vol in volumes
            ]


        elif source == 'redash':
            sf = StarFishRedash()
            volumes = sf.get_vol_stats()
            volumes = [
                {
                    'name': vol['volume_name'],
                    'attrs': {
                        'capacity_tb': vol['capacity_TB'],
                        'free_tb': vol['free_TB'],
                        'used_tb': vol['used_physical_TB'],
                        'file_count': vol['regular_files'],
                    }
                }
                for vol in volumes
            ]
        else:
            raise ValueError('source must be "rest_api" or "redash"')

        # collect user and lab counts, allocation sizes for each volume
        resources = Resource.objects.filter(resource_type__name='Storage')
        # update all tier 0 resources
        for resource in resources:
            resource_name = resource.name.split('/')[0]
            if 'isilon' in resource.name:
                update_volume_information.send(sender=self.__class__, resource=resource)
            else:
                try:
                    volume = [v for v in volumes if v['name'] == resource_name][0]
                except IndexError:
                    logger.warning('no data found for resource %s from source %s', resource.name, source)
                    continue
                except Exception as e:
                    logger.warning('problem updating resource %s with data from source %s: %s',
                        resource.name, source, e
                   )
                    continue
                update_resource_attr_types_from_dict(resource, volume['attrs'])
