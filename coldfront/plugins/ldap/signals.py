import logging
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from coldfront.core.utils.common import import_from_settings
from coldfront.core.field_of_science.models import FieldOfScience
from coldfront.core.project.signals import (
    project_filter_users_to_remove,
    project_preremove_projectuser,
    project_make_projectuser,
    project_create,
    project_post_create,
)
from coldfront.core.project.models import (
    ProjectUserRoleChoice,
    ProjectUserStatusChoice,
    ProjectUser,
)
from coldfront.plugins.ldap.utils import LDAPConn

if 'coldfront.plugins.sftocf' in import_from_settings('INSTALLED_APPS', []):
    from coldfront.plugins.sftocf.signals import (
        starfish_add_aduser,
        starfish_remove_aduser,
        starfish_add_adgroup,
    )


logger = logging.getLogger(__name__)

@receiver(project_create)
def identify_ad_group(sender, **kwargs):
    """Confirm that a project's name corresponds to an existing AD group"""
    project_title = kwargs['project_title']
    try:
        ad_conn = LDAPConn()
        members, manager = ad_conn.return_group_members_manager(project_title)
    except Exception as e:
        logger.exception(
            "error encountered retrieving members and manager for Project %s: %s",
            project_title, e
        )
        raise ValueError(f"ldap error: {e}") from e

    try:
        ifx_pi = get_user_model().objects.get(username=manager['sAMAccountName'][0])
    except Exception as e:
        raise ValueError(f"issue retrieving pi's ifxuser entry: {e}") from e
    return ifx_pi

@receiver(project_post_create)
def update_new_project(sender, **kwargs):
    """Update the new project using the AD group information"""
    project = kwargs['project_obj']
    try:
        ad_conn = LDAPConn()
        members, manager = ad_conn.return_group_members_manager(project.title)
    except Exception as e:
        raise ValueError(f"ldap connection error: {e}")
    # locate field_of_science
    if 'department' in manager.keys() and manager['department']:
        field_of_science_name=manager['department'][0]
        logger.debug('field_of_science_name %s', field_of_science_name)
        field_of_science_obj, created = FieldOfScience.objects.get_or_create(
            description=field_of_science_name, defaults={'is_selectable':'True'}
        )
        if created:
            logger.info('added new field_of_science: %s', field_of_science_name)
    else:
        raise ValueError(f'no department for AD group {project.title}, will not add unless fixed')

    project.field_of_science = field_of_science_obj
    project.pi = get_user_model().objects.get(username=manager['sAMAccountName'][0])
    project.save()
    for member in members:
        role_name = "User" if member['sAMAccountName'][0] != manager['sAMAccountName'][0] else "PI"
        try:
            user_obj = get_user_model().objects.get(username=member['sAMAccountName'][0])
        except get_user_model().DoesNotExist:
            logger.warning('User %s not found when trying to add to Project %s',
                           member['sAMAccountName'][0], project.title)
            continue
        ProjectUser.objects.create(
            project=project,
            user=user_obj,
            role=ProjectUserRoleChoice.objects.get(name=role_name),
            status=ProjectUserStatusChoice.objects.get(name='Active'),
        )
        logger.info('added User %s to Project %s as %s',
                    user_obj.username, project.title, role_name,
                    extra={ 'category': 'database_change:ProjectUser', 'status': 'success' }
        )

@receiver(project_filter_users_to_remove)
def filter_project_users_to_remove(sender, **kwargs):
    users_to_remove = kwargs['users_to_remove']
    usernames = [u['username'] for u in users_to_remove]
    ldap_conn = LDAPConn()
    users_main_group = ldap_conn.users_in_primary_group(usernames, kwargs['project'].title)
    users_to_remove = [
        u for u in users_to_remove if u['username'] not in users_main_group
    ]
    return users_to_remove

@receiver(project_make_projectuser)
def add_user_to_group(sender, **kwargs):
    ldap_conn = LDAPConn()
    ldap_conn.add_user_to_group(kwargs['user_name'], kwargs['group_name'])

@receiver(project_preremove_projectuser)
def remove_member_from_group(sender, **kwargs):
    ldap_conn = LDAPConn()
    ldap_conn.remove_member_from_group(kwargs['user_name'], kwargs['group_name'])

if 'coldfront.plugins.sftocf' in import_from_settings('INSTALLED_APPS', []):
    @receiver(starfish_add_aduser)
    def starfish_add_user(sender, **kwargs):
        ldap_conn = LDAPConn()
        ldap_conn.add_user_to_group(kwargs['username'], 'starfish_users')

    @receiver(starfish_remove_aduser)
    def starfish_remove_user(sender, **kwargs):
        ldap_conn = LDAPConn()
        ldap_conn.remove_member_from_group(kwargs['username'], 'starfish_users')

    @receiver(starfish_add_adgroup)
    def starfish_add_group(sender, **kwargs):
        ldap_conn = LDAPConn()
        ldap_conn.add_group_to_group(kwargs['groupname'], 'starfish_users')
