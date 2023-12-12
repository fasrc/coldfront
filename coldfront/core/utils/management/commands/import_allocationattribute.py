from django.conf import settings
from django.core.management.base import BaseCommand

from coldfront.core.allocation.models import (Allocation, AllocationAttribute,
                                              AllocationAttributeType,
                                              AllocationStatusChoice)
from coldfront.core.resource.models import (Resource,
                                            ResourceAttribute,
                                            ResourceAttributeType)

base_dir = settings.BASE_DIR

class Command(BaseCommand):

    def handle(self, *args, **options):

        allocation_obj, _ = Allocation.objects.get_or_create(
            project=project_obj,
            status=AllocationStatusChoice.objects.get(name='Active'),
            start_date=start_date,
            end_date=end_date,
            justification='Need extra storage for webserver.'
        )


        allocation_attribute_type_obj = AllocationAttributeType.objects.get(
            name='Tier 0')
        allocation_attribute_obj, _ = AllocationAttribute.objects.get_or_create(
            allocation_attribute_type=allocation_attribute_type_obj,
            allocation=allocation_obj,
            value=1888)

        # allocation_attribute_obj.allocationattributeusage.value = 10
        # allocation_attribute_obj.allocationattributeusage.save()



        allocation_obj.resources.add(
            Resource.objects.get(name='University Cloud Storage'))
        allocation_obj.save()


        ResourceAttribute.objects.get_or_create(resource_attribute_type=ResourceAttributeType.objects.get(
        name='quantity_default_value'), resource=Resource.objects.get(name='Budgetstorage'), value=10)
