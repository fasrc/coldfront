'''
Identify AD Groups that do not have a corresponding ColdFront Project and add them.

AD groups to be added are identified by the following criteria:
- AD group is part of Domain Groups
- AD group has a manager who is a current AD User
- AD group is not part of the ColdFront Project Groups
- AD group name has a suffix of _lab or _l3
'''
import logging
from datetime import datetime

from django.core.management.base import BaseCommand

from coldfront.plugins.ldap.utils import (LDAPConn,
                                        cleaned_membership_query,
                                        GroupUserCollection,
                                        add_new_projects)
from coldfront.core.project.models import Project
from coldfront.core.utils.fasrc import update_csv
logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Identify AD Groups that do not have a corresponding ColdFront Project and add them.'

    def handle(self, *args, **options):
        # compare projects in AD to projects in coldfront
        ldap_conn = LDAPConn()
        project_titles = [project.title for project in Project.objects.all()]
        # get all AD groups that have a manager and a name ending in _lab or _l3
        ad_groups = ldap_conn.search_groups({
                        'sAMAccountName': ['*_lab', '*_l3'],
                        'managedBy': '*'
                        }, attributes=['sAMAccountName'])
        ad_group_names = [group['sAMAccountName'][0] for group in ad_groups] # get all AD group names

        ad_only = list(set(ad_group_names) - set(project_titles)) # print AD groups that do not have a corresponding ColdFront project
        errortracker = { 'no_pi': [], 'not_found': [], 'no_fos': [], 'pi_not_projectuser': [], 'pi_active_invalid': [] }
        proj_membs_mans = {name: ldap_conn.return_group_members_manager(name) for name in ad_only}
        proj_membs_mans, search_errors = cleaned_membership_query(proj_membs_mans)
        for k, v in search_errors.items():
            if v in errortracker:
                errortracker[v] += k
            else:
                errortracker[v] = [k]
        groupusercollections = [GroupUserCollection(k, v[0], v[1]) for k, v in proj_membs_mans.items()]

        added_projects, errortracker = add_new_projects(groupusercollections, errortracker)
        print(f"added {len(added_projects)} projects: ", [a[0] for a in added_projects])
        print("errs: ", errortracker)
        not_added = [{'title': i, 'info': k} for k, v in errortracker.items() for i in v]
        update_csv(not_added, 'local_data/', 'unadded_projects.csv')