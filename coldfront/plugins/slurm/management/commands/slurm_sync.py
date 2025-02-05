import sys
import logging
import os
import tempfile

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model

from coldfront.core.project.models import Project
from coldfront.core.allocation.models import (
    AllocationStatusChoice,
    AllocationAttributeType,
    AllocationUserAttributeType,
    AllocationUserStatusChoice,
)
from coldfront.core.resource.models import Resource
from coldfront.plugins.slurm.utils import SlurmError, slurm_dump_cluster
from coldfront.plugins.slurm.associations import SlurmCluster


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Import all Slurm allocations into Coldfront.'

    def add_arguments(self, parser):
        parser.add_argument('-f', '--file',
            help='designate a file with sacctmgr dump data to use as a datasource')

    def _cluster_from_dump(self, cluster, file=None):
        slurm_cluster = None
        if file:
            logger.info("   _cluster_from_dump - Loading from file")
            with open(file) as data:
                logger.info(f"  _cluster_from_dump: {data}")
                slurm_cluster = SlurmCluster.new_from_stream(data)
        else:
            with tempfile.TemporaryDirectory() as tmpdir:
                fname = os.path.join(tmpdir, 'cluster.cfg')
                cluster_name = cluster.get_attribute("slurm_cluster")
                try:
                    slurm_dump_cluster(cluster_name, fname)
                    with open(fname) as fh:
                        logger.debug(f" Loading cluster info from stream")
                        slurm_cluster = SlurmCluster.new_from_stream(fh)
                except SlurmError as e:
                    logger.error(f'Failed to dump Slurm cluster {cluster} {e}')
                    raise
        slurm_cluster.pull_sshare_data()
        return slurm_cluster

    def create_account_allocations_and_attributes(self, cloud_acct_name_attr_type, hours_attr_type,slurm_acct_name_attr_type_obj, user_status_active, cluster, resource):
        def create_project_allocation_attributes(project_allocation, account, cloud_acct_name_attr_type, hours_attr_type, slurm_specs_allocation_attribute_type, slurm_acct_name_attr_type_obj):
            # XDMOD related allocation attributes
            project_allocation.allocationattribute_set.get_or_create(
                # 'slurm_account_name'? XDMOD_ACCOUNT_ATTRIBUTE_NAME
                allocation_attribute_type=cloud_acct_name_attr_type,
                value=name
            )
            project_allocation.allocationattribute_set.get_or_create(
                # 'Cloud Account Name'? XDMOD_CLOUD_PROJECT_ATTRIBUTE_NAME
                allocation_attribute_type=cloud_acct_name_attr_type,
                value=name
            )

            project_allocation.allocationattribute_set.get_or_create(
                allocation_attribute_type=hours_attr_type,
                defaults={'value': 0}
            )
            project_allocation.allocationattribute_set.get_or_create(
                allocation_attribute_type=slurm_acct_name_attr_type_obj,
                value=name
            )

            # Sshare related allocation attributes
            share_data = ','.join(f"{key}={value}" for key, value in account.share_dict.items())
            project_allocation.allocationattribute_set.update_or_create(
                allocation_attribute_type=slurm_specs_allocation_attribute_type,
                defaults={"value": share_data}
            )

        def update_allocation_users(account, project_allocation, user_status_active, slurm_specs_allocationuser_attribute_type):
            for allocationuser in project_allocation.allocationuser_set.filter(status__name='Active'):
                if allocationuser.user.username not in account.users.keys():
                    allocationuser.status = AllocationUserStatusChoice.objects.get(name='Removed')
                    allocationuser.save()
            for user_name, user_account in account.users.items():
                try:
                    user = get_user_model().objects.get(username=user_name)
                except Exception:
                    logger.debug(f'no user found: {user_name}')
                    continue
                alloc_user, _ = project_allocation.allocationuser_set.get_or_create(
                    user=user,
                    defaults={
                        'status': user_status_active, 'unit': 'CPU Hours'
                    }
                )
                share_data = ','.join(f"{key}={value}" for key, value in user_account.share_dict.items())
                alloc_user.allocationuserattribute_set.update_or_create(
                    allocationuser_attribute_type=slurm_specs_allocationuser_attribute_type,
                    value=share_data
                )

        undetected_projects = []
        slurm_specs_allocation_attribute_type = AllocationAttributeType.objects.get(name='slurm_specs')
        slurm_specs_allocationuser_attribute_type = AllocationUserAttributeType.objects.get(name='slurm_specs')
        for name, account in cluster.accounts.items():
            try:
                current_project = Project.objects.get(title=name)
                current_project_allocations = current_project.allocation_set.filter(resources__name=resource.name)
                if not current_project_allocations:
                    new_project_allocation = current_project.allocation_set.create(
                        status=AllocationStatusChoice.objects.get(name='Active'),
                        start_date=timezone.now(),
                        justification= 'slurm_sync',
                        quantity=1
                    )
                    new_project_allocation.resources.add(resource)
                    new_project_allocation.save()
                    project_allocation = new_project_allocation
                elif len(current_project_allocations) == 1:
                    project_allocation = current_project_allocations.first()
                elif len(current_project_allocations) > 1:
                    logger.debug(f'Too many allocations: {current_project_allocations}')
                    logger.debug(
                        f'multiple allocations returned for project {current_project.title} resource {resource.name}',
                        True
                    )
                    continue
                create_project_allocation_attributes(project_allocation, account, cloud_acct_name_attr_type, hours_attr_type, slurm_specs_allocation_attribute_type, slurm_acct_name_attr_type_obj)
                # add allocationusers from account
                update_allocation_users(account, project_allocation, user_status_active, slurm_specs_allocationuser_attribute_type)
            except Project.DoesNotExist:
                undetected_projects.append(name)
                continue

        return undetected_projects

    def handle(self, *args, **options):
        # make new SlurmCluster obj containing the dump from the cluster
        logger.debug("Loading cluster info starts", True)
        file = options['file']
        cluster_resources = Resource.objects.filter(
            resource_type__name='Cluster', is_available=True
        )
        logger.debug(f"  File: {options['file']} - Cluster_resources {cluster_resources}")
        slurm_clusters = {cluster_resource: self._cluster_from_dump(cluster_resource, file=file) for cluster_resource in cluster_resources}
        for slurm_cluster, slurm_cluster_dump  in slurm_clusters.items():
            slurm_cluster_dump.write(sys.stdout)
        slurm_acct_name_attr_type_obj = AllocationAttributeType.objects.get(
            name='slurm_account_name')
        cloud_acct_name_attr_type_obj = AllocationAttributeType.objects.get(
            name='Cloud Account Name')
        hours_attr_type_obj = AllocationAttributeType.objects.get(
            name='Core Usage (Hours)')
        user_status_active = AllocationUserStatusChoice.objects.get(name='Active')
        for resource, cluster in slurm_clusters.items():
            # create an allocation for each account
            undetected_projects = self.create_account_allocations_and_attributes(
                cloud_acct_name_attr_type_obj,
                hours_attr_type_obj,
                slurm_acct_name_attr_type_obj,
                user_status_active,
                cluster,
                resource,
            )
            cluster.append_partitions()
            if undetected_projects:
                logger.debug(f'{resource} Accounts without corresponding projects detected: {undetected_projects}', True)
        logger.debug("Associating Allocations and Cluster Partitions ends", True)

