from django.core.management.base import BaseCommand

from coldfront.core.resource.models import (
    Resource,
    ResourceType,
    AttributeType,
    ResourceAttributeType,
)


class Command(BaseCommand):
    help = 'Add default resource related choices'

    def handle(self, *args, **options):

        for attribute_type in (
            'Active/Inactive', 'Date', 'Int',
            'Public/Private', 'Text', 'Yes/No', 'Attribute Expanded Text',
            'Float',
        ):
            AttributeType.objects.get_or_create(name=attribute_type)

        for resource_attribute_type, attribute_type in (
            ('capacity_tb', 'Float'),
            ('free_tb', 'Float'),
            ('file_count', 'Int'),
            # ('Core Count', 'Int'),
            # ('expiry_time', 'Int'),
            # ('fee_applies', 'Yes/No'),
            # ('Node Count', 'Int'),
            # ('Owner', 'Text'),
            ('quantity_default_value', 'Int'),
            ('quantity_label', 'Text'),
            # ('eula', 'Text'),
            # ('OnDemand','Yes/No'),
            # ('ServiceEnd', 'Date'),
            # ('ServiceStart', 'Date'),
            # ('slurm_cluster', 'Text'),
            # ('slurm_specs', 'Attribute Expanded Text'),
            # ('slurm_specs_attriblist', 'Text'),
            # ('Status', 'Public/Private'),
            # ('Vendor', 'Text'),
            # ('Model', 'Text'),
            # ('SerialNumber', 'Text'),
            # ('RackUnits', 'Int'),
            # ('InstallDate', 'Date'),
            # ('WarrantyExpirationDate', 'Date'),
        ):
            ResourceAttributeType.objects.get_or_create(
                name=resource_attribute_type,
                attribute_type=AttributeType.objects.get(name=attribute_type)
            )

        for resource_type, description in (
            ('Storage', 'Network Storage'),
            ('Storage Tier', 'Storage Tier',),
            ('Cloud', 'Cloud Computing'),
            ('Cluster', 'Cluster servers'),
            # ('Cluster Partition', 'Cluster Partition '),
            # ('Compute Node', 'Compute Node'),
            # ('Server', 'Extra servers providing various services'),
            # ('Software License', 'Software license purchased by users'),
            # ('Storage', 'NAS storage'),
        ):
            ResourceType.objects.get_or_create(
                name=resource_type, description=description)


        storage_tier = ResourceType.objects.get(name='Storage Tier')
        storage = ResourceType.objects.get(name='Storage')

        for name, desc, is_public, rtype, parent_name in (
            ('Tier 0', 'Bulk - Lustre', True, storage_tier, None),
            ('Tier 1', 'Enterprise - Isilon', True, storage_tier, None),
            # ('Tier 2', '', True, storage_tier, None),
            ('Tier 3', 'Attic Storage - Tape', True, storage_tier, None),
            ('holylfs04/tier0', 'Lustre storage in Holyoke data center', True, storage, 'Tier 0'),
            ('holylfs05/tier0', 'Lustre storage in Holyoke data center', True, storage, 'Tier 0'),
            ('nesetape/tier3', 'Cold storage for past projects', True, storage, 'Tier 3'),
            ('holy-isilon/tier1', 'Tier1 storage with snapshots and disaster recovery copy', True, storage, 'Tier 1'),
            ('bos-isilon/tier1', 'Tier1 server in Boston for on-campus mounted storage', True, storage, 'Tier 1'),
            ('holystore01/tier0', 'Luster storage under Tier0', True, storage, 'Tier 0'),
            # ('h-nfs11-p/tier2', 'Holyoke Tier 2 vol 11', True, storage, 'Tier 2'),
            ('h-nfs11-p/tier2', 'Holyoke Tier 2 vol 11', True, storage, None),
            # ('h-nfs12-p/tier2', 'Holyoke Tier 2 vol 12', True, storage, 'Tier 2'),
            ('h-nfs12-p/tier2', 'Holyoke Tier 2 vol 12', True, storage, None),
            # ('h-nfs13-p/tier2', 'Holyoke Tier 2 vol 13', True, storage, 'Tier 2'),
            ('h-nfs13-p/tier2', 'Holyoke Tier 2 vol 13', True, storage, None),
            # ('h-nfs14-p/tier2', 'Holyoke Tier 2 vol 14', True, storage, 'Tier 2'),
            ('h-nfs14-p/tier2', 'Holyoke Tier 2 vol 14', True, storage, None),
            # ('h-nfs15-p/tier2', 'Holyoke Tier 2 vol 15', True, storage, 'Tier 2'),
            ('h-nfs15-p/tier2', 'Holyoke Tier 2 vol 15', True, storage, None),
            # ('h-nfs16-p/tier2', 'Holyoke Tier 2 vol 16', True, storage, 'Tier 2'),
            ('h-nfs16-p/tier2', 'Holyoke Tier 2 vol 16', True, storage, None),
            # ('h-nfs17-p/tier2', 'Holyoke Tier 2 vol 17', True, storage, 'Tier 2'),
            ('h-nfs17-p/tier2', 'Holyoke Tier 2 vol 17', True, storage, None),
            # ('h-nfs18-p/tier2', 'Holyoke Tier 2 vol 18', True, storage, 'Tier 2'),
            ('h-nfs18-p/tier2', 'Holyoke Tier 2 vol 18', True, storage, None),
            # ('h-nfs19-p/tier2', 'Holyoke Tier 2 vol 19', True, storage, 'Tier 2'),
            ('h-nfs19-p/tier2', 'Holyoke Tier 2 vol 19', True, storage, None),
            # ('h-nfs20-p/tier2', 'Holyoke Tier 2 vol 20', True, storage, 'Tier 2'),
            ('h-nfs20-p/tier2', 'Holyoke Tier 2 vol 20', True, storage, None),
        ):
            defaults = {
                'description':desc, 'is_public':is_public, 'resource_type':rtype,
            }
            if parent_name:
                defaults['parent_resource'] = Resource.objects.get(name=parent_name)
            Resource.objects.update_or_create(name=name, defaults=defaults)
