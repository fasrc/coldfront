"""
Check allocations against ATT and SF data both to validate and to automatically
add quota, usage, and users.
"""
import json
import logging
from datetime import datetime

import pandas as pd
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand

from coldfront.config.settings import ENV
from coldfront.core.project.models import ProjectStatusChoice
from coldfront.core.allocation.models import (
    AllocationUser,
    AllocationAttribute,
    AllocationStatusChoice,
    AllocationAttributeType,
    AllocationUserStatusChoice,
)
from coldfront.core.allocation.utils import check_l3_tag
from coldfront.core.utils.fasrc import update_csv, select_one_project_allocation, save_json
from coldfront.core.resource.models import Resource
from coldfront.plugins.sftocf.utils import StarFishRedash, RedashDataPipeline
from coldfront.plugins.fasrc.utils import (
    AllTheThingsConn,
    match_entries_with_projects,
    push_quota_data
)

logger = logging.getLogger(__name__)

class Command(BaseCommand):

    def handle(self, *args, **options):

        added_allocations_df = pd.DataFrame()

        command_report = {
                'allocations_added': [],
                'allocations_existing': [],
                'missing_projects': [],
                }
        # connect and pull quota data
        attconn = AllTheThingsConn()
        # query includes filters
        result_json = attconn.pull_quota_data()
        result_json = attconn.format_query_results(result_json)
        resp_json_by_lab = {entry['lab']:[] for entry in result_json}
        [resp_json_by_lab[e['lab']].append(e) for e in result_json]
        result_file = 'local_data/att_quota_data.json'
        save_json(result_file, resp_json_by_lab)

        # Remove allocations for labs not in Coldfront, add those labs to a list
        result_cleaned, proj_models = match_entries_with_projects(resp_json_by_lab)

        redash_api = StarFishRedash()
        allocation_usages = redash_api.return_query_results(query='subdirectory')

        # make item calls
        subdir_type = AllocationAttributeType.objects.get(name='Subdirectory')
        projectstatuschoice_active = ProjectStatusChoice.objects.get(name='Active')
        allocationstatuschoice_active = AllocationStatusChoice.objects.get(name='Active')
        allocationuserstatuschoice_active = AllocationUserStatusChoice.objects.get(name='Active')
        allocationattrtype_l3tag = AllocationAttributeType.objects.get(name='L3')
        allocationattrtype_payment = AllocationAttributeType.objects.get(
                    name='RequiresPayment')

        for project in proj_models:
            if project.status.name == 'New':
                project.status = projectstatuschoice_active
                project.save()

        for lab, allocations in result_cleaned.items():
            project = proj_models.get(title=lab)
            for entry in allocations:
                lab_name = entry['lab']
                lab_server = entry['server']
                lab_path = entry['fs_path'].replace(f'/n/{entry["server"]}/', '')

                resource = Resource.objects.get(name__contains=entry['server'])
                alloc_obj = select_one_project_allocation(project, resource, lab_path)
                if alloc_obj is not None:
                    continue
                lab_usage_entries = [
                    i for i in allocation_usages if i['vol_name'] == lab_server
                    and lab_path in i['path'] and i['group_name'] == lab_name
                ]
                if not lab_usage_entries:
                    logger.info("No starfish usage data found for %s %s %s", lab_name, lab_server, lab_path)
                    continue

                # don't create allocation if it appears to correspond to an open allocation request
                open_alloc_reqs = project.allocation_set.filter(
                    status__name__in=['New', 'In Progress', 'Pending Activation', 'On Hold'],
                    resources__name=resource.name,
                )
                if open_alloc_reqs.exists():
                    logger.info("Skipping allocation creation for %s %s %s - open allocation request exists",
                                lab_name, lab_server, lab_path)
                    continue

                allocation, created = project.allocation_set.get_or_create(
                    resources__name=resource.name,
                    allocationattribute__value=lab_path,
                    defaults={
                        'status': allocationstatuschoice_active,
                        'start_date': datetime.now(),
                        'is_changeable': resource.is_allocatable,
                        'justification': f'Allocation Information for {lab_name}',
                    }
                )
                # do not modify status of inactive allocations
                allocation_str = f'{lab_name}  {lab_server}  {lab_path}'
                if created:
                    allocation.resources.add(resource)
                    AllocationAttribute.objects.create(
                        allocation=allocation,
                        allocation_attribute_type_id=subdir_type.pk,
                        value=lab_path
                    )
                    AllocationAttribute.objects.create(
                        allocation=allocation,
                        allocation_attribute_type_id=allocationattrtype_payment.pk,
                        value=resource.requires_payment
                    )
                    # if the allocation is new, check whether to add L3 tag
                    if check_l3_tag(allocation, resource):
                        AllocationAttribute.objects.create(
                            allocation=allocation,
                            allocation_attribute_type_id=allocationattrtype_l3tag.pk,
                            value=True
                        )
                    print(f'allocation created: {allocation_str}')
                    logger.info('allocation created: %s', allocation_str)
                    allocation.save()
                    command_report['allocations_added'].append(allocation_str)
                    row = pd.DataFrame({
                        'project_title': lab_name,
                        'server': lab_server,
                        'path': lab_path,
                        'date': datetime.now()
                    }, index=[0])
                    added_allocations_df = pd.concat([added_allocations_df, pd.DataFrame(row)], ignore_index=True)
                else:
                    command_report['allocations_existing'].append(allocation_str)
                    continue
                pi_obj = project.pi
                try:
                    _, created = AllocationUser.objects.get_or_create(
                        allocation=allocation,
                        user=pi_obj,
                        defaults={'status': allocationuserstatuschoice_active}
                    )
                except ValidationError:
                    logger.warning('adding PI %s to allocation %s failed',
                                    pi_obj.pi.username, allocation.pk)
                    created = None
                if created:
                    print('PI added: ' + project.pi.username)
        if not added_allocations_df.empty:
            added_allocations_df['billing_code'] = None
            update_csv(added_allocations_df.to_dict(orient='records'),
                './local_data/', f'added_allocations_{datetime.today().date()}.csv')
        push_quota_data(result_file)
        data_pull = RedashDataPipeline()
        allocationquerymatch_objs, user_models = data_pull.clean_collected_data()
        data_pull.update_coldfront_objects(user_models)
        return json.dumps(command_report, indent=2)
