'''
utility functions for LDAP interaction
'''
import logging

from django.db.models import Q
from django.utils import timezone
from ldap3 import Connection, Server, ALL_ATTRIBUTES

from coldfront.core.utils.common import import_from_settings
from coldfront.core.utils.fasrc import id_present_missing_users
from coldfront.core.project.models import ( Project,
                                            ProjectUserRoleChoice,
                                            ProjectUserStatusChoice,
                                            ProjectUser)

logger = logging.getLogger(__name__)


class LDAPConn:

    def __init__(self):
        self.LDAP_SERVER_URI = import_from_settings('AUTH_LDAP_SERVER_URI', None)
        self.LDAP_BIND_DN = import_from_settings('AUTH_LDAP_BIND_DN', None)
        self.LDAP_BIND_PASSWORD = import_from_settings('AUTH_LDAP_BIND_PASSWORD', None)
        self.LDAP_USER_SEARCH_BASE = import_from_settings('AUTH_LDAP_USER_SEARCH_BASE', None)
        self.LDAP_GROUP_SEARCH_BASE = import_from_settings('AUTH_LDAP_GROUP_SEARCH_BASE', None)
        self.LDAP_CONNECT_TIMEOUT = import_from_settings('LDAP_CONNECT_TIMEOUT', 20)
        self.LDAP_USE_SSL = import_from_settings('AUTH_LDAP_USE_SSL', False)
        self.server = Server(self.LDAP_SERVER_URI, use_ssl=self.LDAP_USE_SSL, connect_timeout=self.LDAP_CONNECT_TIMEOUT)
        print(self.LDAP_SERVER_URI)
        self.conn = Connection(self.server, self.LDAP_BIND_DN, self.LDAP_BIND_PASSWORD, auto_bind=True)

    def search(self, attr_search_dict, search_base, search_type='exact', attributes=ALL_ATTRIBUTES):
        '''Run an LDAP search.

        Parameters
        ----------
        attr_search_dict : dict
            format should be {'cn': 'Bob Smith', 'company': 'FAS'}
        search_base : string
            should appear similar to "ou=Domain Users,dc=mydc,dc=domain"
        search_type : string
            options are 'exact' or 'partial'

        Returns
        -------

        '''
        search_filter = format_template_assertions(attr_search_dict, search_type=search_type)
        search_parameters = {
            'search_base': search_base,
            'search_filter': search_filter,
            'attributes': attributes,
        }
        self.conn.search(**search_parameters)
        return self.conn.entries


    def search_users(self, attr_search_dict, search_type='exact', attributes=ALL_ATTRIBUTES):
        '''search for users.
        '''
        user_entries = self.search( attr_search_dict,
                                    self.LDAP_USER_SEARCH_BASE,
                                    search_type=search_type,
                                    attributes=attributes)
        return user_entries


    def search_groups(self, attr_search_dict, search_type='exact', attributes=ALL_ATTRIBUTES):
        '''search for groups.
        Parameters
        ----------
        attr_search_dict : dict
            format should be {'cn': 'Bob Smith', 'company': 'FAS'}
        search_type : string
            options are 'exact' or 'partial'
        '''
        group_entries = self.search(attr_search_dict,
                                    self.LDAP_GROUP_SEARCH_BASE,
                                    search_type=search_type)
        return group_entries

    def return_group_members(self, group_entry):
        '''return user entries that are members of the specified group.
        '''
        group_dn = group_entry['distinguishedName'].value
        group_members = self.search_users({'memberOf': group_dn})
        return group_members

    def return_group_members_manager(self, samaccountname):
        '''return user entries that are members of the specified group.
        '''
        logger.debug('return_group_members_manager for Project %s', samaccountname)
        group_entries = self.search_groups(
                    {'sAMAccountName': samaccountname},
                    attributes=['managedBy', 'distinguishedName', 'sAMAccountName', 'member']
                    )
        if len(group_entries) > 1:
            return 'multiple groups with same sAMAccountName'
        if not group_entries:
            return 'no matching groups found'
        group_entry = group_entries[0]
        group_dn = group_entry['distinguishedName'].value
        group_members = self.search_users(
                    {'memberOf': group_dn},
                    attributes=['sAMAccountName', 'cn', 'name', 'title',
                                'distinguishedName', 'accountExpires', 'info',
                                'memberOf',
                                ])
        logger.debug('group_members:\n%s', group_members)
        try:
            group_manager_dn = group_entry['managedBy'].value
        except Exception as e:
            return 'no manager specified'
        group_manager = self.search_users({'distinguishedName': group_manager_dn})[0]
        logger.debug('group_manager:\n%s', group_manager)
        if not group_manager:
            return 'no manager found'
        return (group_members, group_manager)


    def create_user(self, fullname, additional_orgs=None, object_class=None, attributes=None):
        '''Create a new AD user.
        Note: the LDAP protocol doesn’t support NULL values. If you try to add
        an attribute with an empty value or a multi-valued attributes with all
        empty values, the attribute won’t be created.
        '''
        additional_ous = ','.join([f'ou={ou}' for ou in additional_orgs])
        distinguished_name = f"CN={fullname},{additional_ous},{self.LDAP_USER_SEARCH_BASE}"
        self.conn.add(  distinguished_name,
                        object_class=object_class,
                        attributes=attributes
                        )


def format_template_assertions(attr_search_dict, search_type='exact', search_operator='and'):
    '''Format attr_search_string_dict into correct filter_template
    Parameters
    ----------
    attr_search_dict : dict
        format should be {'cn': 'Bob Smith', 'company': 'FAS'}
    search_type : str
        options are 'exact' or 'partial'
    search_operator : str
        options are 'and' or 'or'

    Returns
    -------
    output should be string formatted like '(|(cn=Bob Smith)(company=FAS))'

    '''
    match_type = {'exact':'', 'partial': '*'}
    match_operator = {'and':'&', 'or':'|'}
    filter_template_vars = [
                f'({k}={match_type[search_type]}{v}{match_type[search_type]})'
                for k, v in attr_search_dict.items()]
    search_filter = ''.join(filter_template_vars)
    if len(filter_template_vars) > 1:
        search_filter = f'({match_operator[search_operator]}'+search_filter+')'
    return search_filter


def collect_update_group_membership():
    '''
    Update Coldfront ProjectUser entries for existing Coldfront Projects using
    ADGroup data.
    '''

    errors = { 'no_users': [], 'no_managers': [] }

    # collect commonly used db objects
    projectuser_role_user = ProjectUserRoleChoice.objects.get(name='User')
    projectuserstatus_active = ProjectUserStatusChoice.objects.get(name='Active')
    projectuserstatus_removed = ProjectUserStatusChoice.objects.get(name='Removed')
    projectuser_role_manager = ProjectUserRoleChoice.objects.get(name='Manager')

    ad_conn = LDAPConn()

    projectuser_status_updates = []
    projectuser_role_updates = []

    for project in Project.objects.filter(status__name__in=['Active', 'New']).prefetch_related('projectuser_set'):
        # pull membership data for the given project
        proj_name = project.title
        logger.debug('updating group membership for %s', proj_name)
        all_members, pi = ad_conn.return_group_members(proj_name)
        logger.debug('raw AD group data:\n%s', all_members)


        ### check PI ###
        if not pi:
            logger.warning('no active managers for project %s', proj_name)
            print(f'WARNING: no active managers for project {proj_name}')
            errors['no_managers'].append(proj_name)
            continue
        pi_name = [p['sAMAccountName'].value for p in pi][0]

        # ensure that role is set to manager
        project_manager = project.projectuser_set.get(user__username=pi_name)
        project_manager.role = projectuser_role_manager
        projectuser_role_updates.append(project_manager)

        ### limit returned members to those without an expired account ###
        members = [mem for mem in all_members if mem['accountExpires'].value > timezone.now()]

        ### check presence of ADGroup members in Coldfront  ###
        proj_usernames = [pu.user.username for pu in project.projectuser_set.filter(
                    (~Q(status__name='Removed'))
                            )]
        logger.debug('projectusernames: %s', proj_usernames)

        if members:
            ad_users = [u['sAMAccountName'].value for u in members]
        else:
            logger.warning('WARNING: NO USERS LISTED FOR %s', project.title)
            errors['no_users'].append(proj_name)
            ad_users = []

        # check for users not in Coldfront
        not_added = [uname for uname in ad_users if uname not in proj_usernames]
        logger.debug('AD users not in ProjectUsers:\n%s', not_added)

        if not_added:
            # find accompanying ifxusers in the system and add as ProjectUsers
            ifxusers, missing_users = id_present_missing_users(not_added)
            # log missing IFXusers
            # log_missing('users', missing_users)

            # If user is missing because status was changed to "removed", update status
            present_users = project.projectuser_set.filter(user__in=ifxusers)
            present_users.update(   role=projectuser_role_user,
                                    status=projectuserstatus_active)
            presentusers_ids = present_users.values_list('user__id', flat=True)
            # create new entries for all new ProjectUsers
            missing_projectusers = ifxusers.exclude(id__in=presentusers_ids)
            ProjectUser.objects.bulk_create([ProjectUser(
                                                project=project,
                                                user=user,
                                                role=projectuser_role_user,
                                                status=projectuserstatus_active
                                            )
                                            for user in missing_projectusers
                                ])

        ### change statuses of inactive ProjectUsers to 'Removed' ###
        projusers_to_remove = [uname for uname in proj_usernames if uname not in ad_users]
        if projusers_to_remove:
            # log removed users
            logger.debug('users to remove: %s', projusers_to_remove)

            # change ProjectUser status to Removed
            for username in projusers_to_remove:
                project_user = project.projectuser_set.get(user__username=username)
                project_user.status = projectuserstatus_removed
                projectuser_status_updates.append(project_user)
                logger.debug('removed User %s from Project %s', username, project.title)
    ProjectUser.objects.bulk_update(projectuser_status_updates, ['status'])
    ProjectUser.objects.bulk_update(projectuser_role_updates, ['role'])
    logger.warning('errorlist: %s', errors)
