"""Add, update, and remove Starfish zones
- Add zones/zone paths
    - Collect all projects that have active allocations on Starfish
    - separate projects by whether a zone with the same name currently exists
    - Create zones for all projects that don’t yet exist
    - For the projects that do have zones, ensure that the corresponding zone:
        - has the project AD group in “managing_groups”
        - has all the allocation paths associated with the project
- Remove zones/zone paths
    - Collect all projects with allocations that were deactivated since the last successful run of the DjangoQ task, or in the past week
    - If the project no longer has any active allocations on Starfish, remove the zone
"""
import logging
from requests.exceptions import HTTPError

from django.core.management.base import BaseCommand

from coldfront.core.project.models import Project, ProjectAttributeType
from coldfront.plugins.sftocf.utils import (
    StarFishServer, ZoneCreationError,
)

logger = logging.getLogger(__name__)
class Command(BaseCommand):
    help = 'Add, update, and remove Starfish zones based on Coldfront projects'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Do not make any changes to Starfish, just print what changes would be slated',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            print("DRY RUN")

        report = {
            'dry_run': dry_run,
            'deleted_zones': [],
            'created_zones': [],
            'allocations_missing_paths': [],
            'updated_zone_paths': [],
            'updated_zone_groups': []
        }

        sf = StarFishServer()
        starfish_zone_attr_type = ProjectAttributeType.objects.get(name='Starfish Zone')
        # collect all projects that have active allocations on Starfish
        projects_with_allocations = Project.objects.filter(
            allocation__status__name='Active',
            allocation__resources__in=sf.get_corresponding_coldfront_resources(),
        ).distinct()

        # also confirm that the projects are available as groups in Starfish
        projects_with_allocations = projects_with_allocations.filter(
            title__in=sf.get_groups(),
        )

        projects_with_zones = projects_with_allocations.filter(
            projectattribute__proj_attr_type=starfish_zone_attr_type,
        )
        # for the projects that do have zones, ensure that its zone:
        sf_cf_vols = sf.get_volumes_in_coldfront()
        for project in projects_with_zones:
            zone_id = project.projectattribute_set.get(
                proj_attr_type__name='Starfish Zone',
            ).value
            zone = sf.get_zones(zone_id)

            # has all the allocation paths associated with the project
            update_paths = zone['paths']
            storage_allocations = project.allocation_set.filter(
                status__name='Active',
                resources__in=sf.get_corresponding_coldfront_resources(),
            )
            zone_paths_not_in_cf = [p for p in zone['paths'] if p.split(':')[0] not in sf_cf_vols]
            # don't update if any paths are missing
            missing_paths = False
            for a in storage_allocations:
                if a.path == '':
                    missing_paths = True
                    report['allocations_missing_paths'].append(a.pk)
                    logger.error('Allocation %s (%s) is missing a path; cannot update zone until this is fixed',
                        a.pk, a)
            if missing_paths:
                continue
            paths = [f'{a.resources.first().name.split("/")[0]}:{a.path}' for a in storage_allocations] + zone_paths_not_in_cf
            # delete any zones that have no paths
            if not paths:
                if not dry_run:
                    sf.delete_zone(zone['name'])
                    # delete projectattribute
                    project.projectattribute_set.get(
                        proj_attr_type=starfish_zone_attr_type,
                    ).delete()
                report['deleted_zones'].append(zone['name'])
                continue
            if not set(paths) == set(zone['paths']):
                if not dry_run:
                    update_paths['paths'] = paths
                    sf.update_zone(zone['name'], paths=update_paths)
                report['updated_zone_paths'].append({
                    'zone': zone['name'],
                    'old_paths': zone['paths'],
                    'new_paths': paths,
                })

            # has the project AD group in “managing_groups”
            update_groups = zone['managing_groups']
            zone_group_names = [g['groupname'] for g in zone['managing_groups']]
            if project.title not in zone_group_names:
                if not dry_run:
                    update_groups.append({'groupname': project.title})
                    sf.update_zone(zone, managing_groups=update_groups)
                report['updated_zone_groups'].append({
                    'zone': zone['name'],
                    'old_groups': zone_group_names,
                    'new_groups': zone_group_names + [project.title],
                })
                
        # if project lacks "Starfish Zone" attribute, create or update the zone and save zone id to ProjectAttribute "Starfish Zone"
        projects_without_zones = projects_with_allocations.exclude(
            projectattribute__proj_attr_type=starfish_zone_attr_type,
        )
        for project in projects_without_zones:
            if not dry_run:
                try:
                    zone = sf.zone_from_project(project)
                    report['created_zones'].append(project.title)
                except HTTPError as e:
                    if e.response.status_code == '409':
                        logger.warning('zone for %s already exists; adding zoneid to Project and breaking', project.title)
                        zone = sf.get_zone_by_name(project.title)
                    else:
                        logger.error(
                            'unclear error prevented creation of zone for project %s. error: %s',
                            project.title, e
                        )
                project.projectattribute_set.get_or_create(
                    proj_attr_type=starfish_zone_attr_type,
                    value=zone['id'],
                )
            else:
                report['created_zones'].append(project.title)
        print(report)
        logger.warning(report)
