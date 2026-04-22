"""LDAP signals and mail when a project user's manager role changes."""

import logging

from coldfront.core.project.signals import (
    project_user_manager_ldap_groups_grant,
    project_user_manager_ldap_groups_revoke,
)
from coldfront.core.utils.common import import_from_settings
from coldfront.core.utils.mail import (
    build_link,
    email_template_context,
    send_email_template,
)

logger = logging.getLogger(__name__)

EMAIL_SENDER = import_from_settings('EMAIL_SENDER')
EMAIL_TICKET_SYSTEM_ADDRESS = import_from_settings('EMAIL_TICKET_SYSTEM_ADDRESS')

MANAGER_ROLES = frozenset({'General Manager', 'Storage Manager', 'Access Manager'})


def is_manager_role(role_name):
    return role_name in MANAGER_ROLES


def _role_change_flags(old_role, new_role):
    old_mgr = is_manager_role(old_role)
    new_mgr = is_manager_role(new_role)
    return {
        'gained_manager': (not old_mgr) and new_mgr,
        'lost_manager': old_mgr and (not new_mgr),
        'manager_role_reassigned': old_mgr and new_mgr,
        'new_mgr': new_mgr,
    }


def build_project_role_change_context(
    project,
    project_user,
    old_role,
    new_role,
    requester_username,
):
    """Context for ``email/project_role_change.txt``"""
    flags = _role_change_flags(old_role, new_role)
    show_manager_powers = (
        (flags['gained_manager'] or flags['manager_role_reassigned']) and flags['new_mgr']
    )
    return email_template_context(
        extra_context={
            'project_title': project.title,
            'username': project_user.user.username,
            'user_email': project_user.user.email,
            'old_role': old_role,
            'new_role': new_role,
            'role_changer': requester_username,
            'project_url': build_link(f'project/{project.pk}/'),
            'show_manager_powers': show_manager_powers,
            **flags,
        }
    )


def notify_manager_role_transition(
    *,
    project_user,
    old_role,
    new_role,
    requester_username,
    project,
):
    """LDAP group sync, helpdesk ticket, and user email when the project role changes."""
    if old_role == new_role:
        return

    old_mgr = is_manager_role(old_role)
    new_mgr = is_manager_role(new_role)
    username = project_user.user.username
    project_title = project.title

    signal_dict = {
        'sender': notify_manager_role_transition,
        'user_name': username,
        'project_title': project_title,
    }

    if not old_mgr and new_mgr:
        project_user_manager_ldap_groups_grant.send(**signal_dict)
    elif old_mgr and not new_mgr:
        project_user_manager_ldap_groups_revoke.send(**signal_dict)

    template_context = build_project_role_change_context(
        project,
        project_user,
        old_role,
        new_role,
        requester_username,
    )

    send_email_template(
        subject=f'Role Change for User {username} in Project {project_title}',
        template_name='email/project_role_change.txt',
        template_context=template_context,
        sender=EMAIL_SENDER,
        receiver_list=[project_user.user.email],
        cc=[project.pi.email],
    )
