'''
utility functions for LDAP interaction
'''
import logging
import operator
from functools import reduce

from django.db.models import Q
from django.utils import timezone
from django.contrib.auth import get_user_model
from ldap3 import Connection, Server, ALL_ATTRIBUTES

from coldfront.core.utils.common import import_from_settings
from coldfront.core.field_of_science.models import FieldOfScience
from coldfront.core.utils.fasrc import id_present_missing_users, log_missing
from coldfront.core.project.models import ( Project,
                                            ProjectStatusChoice,
                                            ProjectUserRoleChoice,
                                            ProjectUserStatusChoice,
                                            ProjectUser)

logger = logging.getLogger(__name__)


class LDAPConn:
    '''
    LDAP connection object
    '''
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
            should appear similar to 'ou=Domain Users,dc=mydc,dc=domain'
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
        attributes=ALL_ATTRIBUTES, return_as='dict'):
        '''search for users.
        '''
        user_entries = self.search( attr_search_dict,
                                    self.LDAP_USER_SEARCH_BASE,
                                    search_type=search_type,
                                    attributes=attributes)
        if return_as == 'dict':
            user_entries = [e.entry_attributes_as_dict for e in user_entries]
        return user_entries


    def search_groups(self, attr_search_dict, search_type='exact',
        attributes=ALL_ATTRIBUTES, return_as='dict'):
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
        if return_as == 'dict':
            group_entries = [e.entry_attributes_as_dict for e in group_entries]
        return group_entries

    def return_group_members(self, group_entry):
        '''return user entries that are members of the specified group.
        '''
        group_dn = group_entry['distinguishedName']
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
        group_dn = group_entry['distinguishedName'][0]
        group_members = self.search_users(
                    {'memberOf': group_dn},
                    attributes=['sAMAccountName', 'cn', 'name', 'title',
                 'distinguishedName', 'accountExpires', 'info'
                                     ])
        logger.debug('group_members:\n%s', group_members)
        try:
            group_manager_dn = group_entry['managedBy'][0]
        except Exception as e:
            return 'no manager specified'
        group_manager = self.search_users({'distinguishedName': group_manager_dn},
                attributes=['sAMAccountName', 'cn', 'name', 'title',
                    'distinguishedName', 'accountExpires', 'info', 'memberOf',
                                 ])
        logger.debug('group_manager:\n%s', group_manager)
        if not group_manager:
            return 'no ADUser manager found'
        return (group_members, group_manager[0])


class GroupUserCollection:
    '''
    Class to hold a group and its members.
    '''
    def __init__(self, group_name, ad_users, pi, project=None):
        self.name = group_name
        self.members = ad_users
        self.pi = pi
        self.project = project
        # self.project, self.new =

    @property
    def current_ad_users(self):
        return [u for u in self.members if u['accountExpires'][0] > timezone.now()]

    @property
    def pi_is_active(self):
        return  self.pi['accountExpires'][0] > timezone.now()

    def compare_active_members_projectusers(self):
        ### check presence of ADGroup members in Coldfront  ###
        logger.debug('membership data collected for %s\nraw ADUser data for %s users',
        self.name, len(self.members))
        if self.current_ad_users:
            logger.debug('(%s of %s users valid)', len(self.current_ad_users), len(self.members))
            ad_users = [u['sAMAccountName'][0] for u in self.current_ad_users]
        else:
            logger.warning('WARNING: NO AD USERS RETURNED FOR %s', self.project.title)
            ad_users = []
        proj_usernames = [pu.user.username for pu in self.project.projectuser_set.filter(
                    (~Q(status__name='Removed')))]
        logger.debug('projectusernames: %s', proj_usernames)

        ad_users_not_added, _, remove_projuser_names = uniques_and_intersection(ad_users, proj_usernames)
        return (ad_users_not_added, remove_projuser_names)


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

def uniques_and_intersection(list1, list2):
    intersection = list(set(list1) & set(list2))
    list1_unique = list(set(list1) - set(list2))
    list2_unique = list(set(list2) - set(list1))
    return (list1_unique, intersection, list2_unique)


def is_string(value):
    return isinstance(value, str)

def is_dict(value):
    return isinstance(value, dict)


def sort_by(list1, sorter, how='attr'):
    is_true, is_false = [], []
    for x in list1:
        if how == 'attr':
            (is_false, is_true)[getattr(x, sorter)].append(x)
        elif how == 'condition':
            (is_false, is_true)[sorter(x)].append(x)
        else:
            raise Exception('unclear sorting method')
    return is_true, is_false

def sort_dict_on_conditional(dict1, condition):
    '''split one dictionary into two, divided by each value's ability to meet a
    condition
    '''
    is_true, is_false = {}, {}
    for k, v in dict1.items():
        (is_false, is_true)[condition(v)][k] = v
    return is_true, is_false

def cleaned_membership_query(proj_membs_mans):
    '''Remove
    '''
    search_errors, proj_membs_mans = sort_dict_on_conditional(proj_membs_mans, is_string)
    if search_errors:
        logger.error('could not return members and manager for some groups:\n%s',
                        search_errors)
    return proj_membs_mans, search_errors

def prep_clean_pi_projects(groupusercollections):
    '''Remove projects that have inactive pis'''
    active_pi_groups, inactive_pi_groups = sort_by(groupusercollections, 'pi_is_active', how='attr')
    if len(active_pi_groups) < len(groupusercollections):
        logger.error('LDAP query returns Active Projects with expired PIs: %s',
        {group.name: group.pi['sAMAccountName'][0] for group in inactive_pi_groups})
    return active_pi_groups

def flatten(l):
    return [item for sublist in l for item in sublist]


def collect_update_group_membership():
    '''
    Update Coldfront ProjectUser entries for existing Coldfront Projects using
    ADGroup data.
    '''

    # collect commonly used db objects
    projectuser_role_user = ProjectUserRoleChoice.objects.get(name='User')
    projectuserstatus_active = ProjectUserStatusChoice.objects.get(name='Active')
    projectusers_to_remove = []

    active_projects = Project.objects.filter(status__name__in=['Active', 'New']).prefetch_related('projectuser_set')

    ad_conn = LDAPConn()

    proj_membs_mans = { proj: ad_conn.return_group_members_manager(proj.title) for proj in active_projects}
    proj_membs_mans, search_errors = cleaned_membership_query(proj_membs_mans)
    groupusercollections = [GroupUserCollection(k.title, v[0], v[1], project=k) for k, v in proj_membs_mans.items()]

    active_pi_groups = prep_clean_pi_projects(groupusercollections)

    ### identify PIs with incorrect roles and change their status ###
    projectuser_role_manager = ProjectUserRoleChoice.objects.get(name='Manager')

    pis_mislabeled = ProjectUser.objects.filter(
        reduce(operator.or_,
            ((  Q(project=group.project) &
                Q(user__username=group.pi['sAMAccountName']) &
                ~Q(role=projectuser_role_manager))
            for group in active_pi_groups)
            )
        )

    if pis_mislabeled:
        logger.info('Project PIs with incorrect labeling: %s',
            [(pi.project.title, pi.user.username) for pi in pis_mislabeled])

        ProjectUser.objects.bulk_update([
            ProjectUser(id=pi.id, role=projectuser_role_manager)
            for pi in pis_mislabeled
        ], ['role'])

    for group in active_pi_groups:

        ad_users_not_added, remove_projuser_names = group.compare_active_members_projectusers()

        # handle any AD users not in Coldfront
        if ad_users_not_added:
            logger.debug('ADUsers not in ProjectUsers:\n%s', ad_users_not_added)
            # find accompanying ifxusers in the system and add as ProjectUsers
            ifxusers, missing_users = id_present_missing_users(ad_users_not_added)
            # log_missing('users', missing_users) # log missing IFXusers

            # If user is missing because status was changed to 'removed', update status
            present_users = group.project.projectuser_set.filter(user__in=ifxusers)
            if present_users:
                logger.warning('found reactivated ADUsers for project %s: %s',
                    group.project.title, [user.user.username for user in present_users])

                present_users.update(role=projectuser_role_user,
                                    status=projectuserstatus_active)
            # create new entries for all new ProjectUsers
            missing_projectusers = ifxusers.exclude(id__in=[pu.pk for pu in present_users])
            ProjectUser.objects.bulk_create([ProjectUser(
                                                project=group.project,
                                                user=user,
                                                role=projectuser_role_user,
                                                status=projectuserstatus_active
                                            )
                                            for user in missing_projectusers
                                ])

        ### identify inactive ProjectUsers, slate for status change ###
        projusers_to_remove = group.project.projectuser_set.filter(
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

def import_projects_projectusers(projects_list):
    '''Use AD user and group information to automatically create new
    Coldfront Projects from projects_list.
    '''
    errortracker = { 'no_pi': [], 'not_found': [] }
    # if project already exists, end here
    existing_projects = Project.objects.filter(title__in=projects_list)
    if existing_projects:
        logger.debug('existing projects: %s', [p.title for p in existing_projects])
    projects_to_add = [p for p in projects_list if p not in [p.title for p in existing_projects]]

    ad_conn = LDAPConn()
    proj_membs_mans = {proj: ad_conn.return_group_members_manager(proj) for proj in projects_to_add}
    proj_membs_mans, search_errors = cleaned_membership_query(proj_membs_mans)
    errortracker['not_found'] = search_errors
    groupusercollections = [GroupUserCollection(k, v[0], v[1]) for k, v in proj_membs_mans.items()]

    added_projects, errortracker = add_new_projects(groupusercollections, errortracker)
    return added_projects, errortracker


def add_new_projects(groupusercollections, errortracker):
    '''create new Coldfront Projects and ProjectUsers from PI and AD user data
    already collected from ATT.
    '''
    # if PI is inactive, don't add project
    active_pi_groups = prep_clean_pi_projects(groupusercollections)

    # identify all users not in ifx
    user_entries = flatten([[group.members, group.pi] for group in active_pi_groups])
    user_names = {u['sAMAccountName'][0] for u in user_entries}
    _, missing_users = id_present_missing_users(user_names)
    log_missing('user', missing_users)
    missing_usernames = [d['username'] for d in missing_users]

    active_present_pi_groups = [group.name for group in active_pi_groups
        if group.pi['sAMAccountName'][0] not in missing_usernames]
    # record and remove projects where pis aren't available
    errortracker['no_pi'] = [group.name for group in groupusercollections
        if group not in active_present_pi_groups]

    for group in active_present_pi_groups:
        logger.debug('source: %s\n%s\n%s', group.name, group.members, group.pi)
        # collect group membership entries
        ad_member_usernames = [
            user['sAMAccountName'][0] for user in group.current_ad_users] - missing_usernames

        # locate field_of_science
        if 'department' in group.pi.keys() and group.pi['department'][0] is not None:
            field_of_science_name=group.pi['department'][0]
            logger.debug('field_of_science_name %s', field_of_science_name)
            field_of_science_obj, created = FieldOfScience.objects.get_or_create(
                            description=field_of_science_name,
                            defaults={'is_selectable':'True'}
                            )
            if created:
                logger.info('added new field_of_science: %s', field_of_science_name)
        else:
            logger.warning('no department for PI of project %s', group.name)
            print(f'WARNING: no field of science for PI of project {group.name}')
            field_of_science_obj = None


        ### CREATE PROJECT ###
        project_pi = get_user_model().objects.get(username=group.pi['sAMAccountName'][0])
        current_dt = timezone.now()
        description = f'Allocations for {group.name}'

        group.project = Project.objects.create(
            created=current_dt,
            modified=current_dt,
            title=group.name,
            pi=project_pi,
            description=description.strip(),
            field_of_science=field_of_science_obj,
            requires_review=False,
            status=ProjectStatusChoice.objects.get(name='New')
        )
        ### add projectusers ###
        # use set comprehension to avoid duplicate entries when MemberOf/ManagedBy
        # relationships both exist
        users_to_add = get_user_model().objects.filter(username__in=ad_member_usernames)
        added_projectusers = ProjectUser.objects.bulk_create([
                ProjectUser(
                        project=group.project,
                        user=user,
                        status=ProjectUserStatusChoice.objects.get(name='Active'),
                        role=ProjectUserRoleChoice.objects.get(name='User'),
                        )
                for user in users_to_add
            ])
        logger.debug('added projectusers: %s', added_projectusers)
        # add permissions to PI/manager-status ProjectUsers
        logger.debug('adding manager status to ProjectUser %s for Project %s',
                    group.pi['sAMAccountName'][0], group.name)
        manager = group.project.projectuser_set.get(user__username=group.pi['sAMAccountName'][0])
        manager.role = ProjectUserRoleChoice.objects.get(name='Manager')
        manager.save()

    added_projects = [group.project for group in active_present_pi_groups]
    for errortype in errortracker:
        logger.warning('AD groups with %s: %s', errortype, errortracker[errortype])
    return added_projects, errortracker
