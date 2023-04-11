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


    def search_users(self, attr_search_dict, search_type='exact',
        attributes=ALL_ATTRIBUTES):
        '''search for users.
        '''
        user_entries = self.search( attr_search_dict,
                                    self.LDAP_USER_SEARCH_BASE,
                                    search_type=search_type,
                                    attributes=attributes)
        return user_entries


    def search_groups(self, attr_search_dict, search_type='exact',
        attributes=ALL_ATTRIBUTES):
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
                                    search_type=search_type,
                                    attributes=attributes)
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
                    attributes=['managedBy', 'distinguishedName',
                                'sAMAccountName', 'member']
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
                 'distinguishedName', 'accountExpires', 'info'
                                     ])
        logger.debug('group_members:\n%s', group_members)
        try:
            group_manager_dn = group_entry['managedBy'].value
        except Exception as e:
            return 'no manager specified'
        group_manager = self.search_users({'distinguishedName': group_manager_dn},
                attributes=['sAMAccountName', 'cn', 'name', 'title',
                    'distinguishedName', 'accountExpires', 'info', 'memberOf',
                                 ])
        logger.debug('group_manager:\n%s', group_manager)
        if not group_manager:
            return 'no manager found'
        return (group_members, group_manager[0])


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

def projectuser_from_manager_uname(project, manager_name):
    '''return project user from an AD Group's manager sAMAccountName'''
    manager_projectuser = project.projectuser_set.get(user__username=manager_name)
    return manager_projectuser

def uniques_and_intersection(list1, list2):
    intersection = list(set(list1) & set(list2))
    list1_unique = list(set(list1) ^ set(intersection))
    list2_unique = list(set(list2) ^ set(intersection))
    return (list1_unique, intersection, list2_unique)


def account_expired_condition(entry):
    return entry['accountExpires'].value < timezone.now()

def is_string(value):
    return isinstance(value, str)

def sort_by_conditional(list1, condition):
    is_true, is_false = [], []
    for x in list1:
        (is_false, is_true)[condition(x)].append(x)
    return is_true, is_false

def sort_dict_on_conditional(dict1, condition):
    '''split one dictionary into two, divided by each value's ability to meet a
    condition
    '''
    is_true, is_false = {}, {}
    for k, v in dict1.items():
        (is_false, is_true)[condition(v)][k] = v
    return is_true, is_false


def collect_update_group_membership():
    '''
    Update Coldfront ProjectUser entries for existing Coldfront Projects using
    ADGroup data.
    '''

    # collect commonly used db objects
    projectuser_role_user = ProjectUserRoleChoice.objects.get(name='User')
    projectuserstatus_active = ProjectUserStatusChoice.objects.get(name='Active')
    projectusers_to_remove = []

    ad_conn = LDAPConn()

    active_projects = Project.objects.filter(status__name__in=['Active', 'New']).prefetch_related('projectuser_set')
    proj_membs_mans = {
        proj: ad_conn.return_group_members_manager(proj.title) for proj in active_projects}
    search_errors, proj_membs_mans = sort_dict_on_conditional(proj_membs_mans, is_string)
    if search_errors:
        logger.error('could not return members and manager for some groups:\n%s',
                        search_errors)

    ### identify PIs with incorrect roles and change their status ###
    projects_pis = {group: membs_mans[1] for group, membs_mans in proj_membs_mans.items()}
    expired_pis, projects_pis = sort_dict_on_conditional(projects_pis, account_expired_condition)
    if expired_pis:
        logger.error("LDAP query returns Active Projects with expired PIs: %s",
        {proj: pi['sAMAccountName'].value for proj, pi in expired_pis})

    projectuser_role_manager = ProjectUserRoleChoice.objects.get(name='Manager')
    pis = [ projectuser_from_manager_uname(project, pi['sAMAccountName'].value)
                            for project, pi in projects_pis.items()]
    pis_mislabeled = [pi for pi in pis if pi.role != projectuser_role_manager]
    if pis_mislabeled:
        logger.info("Project PIs with incorrect labeling: %s",
            [(pi.project.title, pi.user.username) for pi in pis_mislabeled])

        ProjectUser.objects.bulk_update([
            ProjectUser(id=pi.id, role=projectuser_role_manager)
            for pi in pis_mislabeled
        ], ['role'])

    projects_users = {project: users_pi[0] for project, users_pi in proj_membs_mans.items()}
    for project, all_members in projects_users.items():

        ### limit returned members to those without an expired account ###
        members = [mem for mem in all_members if mem['accountExpires'].value > timezone.now()]
        logger.debug('updating group membership for %s\nraw AD group data for %s users (%s valid)',
        project.title, len(all_members), len(members))

        if members:
            ad_users = [u['sAMAccountName'].value for u in members]
        else:
            logger.warning('WARNING: NO AD USERS RETURNED FOR %s', project.title)
            ad_users = []

        ### check presence of ADGroup members in Coldfront  ###
        proj_usernames = [pu.user.username for pu in project.projectuser_set.filter(
                    (~Q(status__name='Removed')))]
        logger.debug('projectusernames: %s', proj_usernames)

        ad_users_not_added, _, remove_projuser_names = uniques_and_intersection(ad_users, proj_usernames)

        # handle any AD users not in Coldfront
        if ad_users_not_added:
            logger.debug('AD users not in ProjectUsers:\n%s', ad_users_not_added)
            # find accompanying ifxusers in the system and add as ProjectUsers
            ifxusers, missing_users = id_present_missing_users(ad_users_not_added)
            # log_missing('users', missing_users) # log missing IFXusers

            # If user is missing because status was changed to "removed", update status
            present_users = project.projectuser_set.filter(user__in=ifxusers)
            if present_users:
                logger.warning('found deactivated project_users for project %s: %s',
                    project.title, [user.user.username for user in present_users])
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

        ### identify inactive ProjectUsers, slate for status change ###
        projusers_to_remove = project.projectuser_set.filter(
                                user__username__in=remove_projuser_names)
        projectusers_to_remove.extend(list(projusers_to_remove))

    ### update status of projectUsers slated for removal ###
    # change ProjectUser status to Removed
    projectuserstatus_removed = ProjectUserStatusChoice.objects.get(name='Removed')
    ProjectUser.objects.bulk_update([
        ProjectUser(id=pu.id, status=projectuserstatus_removed)
        for pu in projectusers_to_remove
    ], ['status'])
    logger.info('changing status of these ProjectUsers to "Removed":%s',
            [(pu.user.username, pu.project.title) for pu in projectusers_to_remove])
