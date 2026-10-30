"""
Apply ProjectUser status changes to AD from the ProjectUser pre_save, whatever saved the row.

| Change                          | AD write                                   | intent     |
|---------------------------------|--------------------------------------------|------------|
| Deactivated -> Active           | reactivate the AD account                  | reactivate |
| any other status -> Active      | add the user to the project's AD group     | add        |
| -> Removed                      | remove the user from the group             | remove     |
| anything else                   | none                                       |            |

A caller can set ``projectuser._ad_intent`` to override the table; the remove view sets
``deactivate`` for a primary-group removal (status Deactivated, AD remove_member_from_group,
which deactivates the account). For removals, AD decides: if the project's group is the user's
primary group the account is deactivated and the row becomes Deactivated, otherwise the
membership is removed and the row becomes Removed, whichever the caller expected.
``projectuser._ad_actor = (username, role)`` is passed to AD for the account info note.
``projectuser._skip_ad_sync = True`` skips AD entirely; saves that mirror AD rather than change
it set it. ``projectuser._ad_complete_removal = True`` (set by the remove view) makes a queued
removal run the view's removal follow-ups (allocations, Slurm, emails) once AD succeeds.

If AD rejects the change, the save is blocked with a ProjectUserStatusChangeError. If AD is
unreachable, the row is saved as Pending - Add / Pending - Remove, ``projectuser._ad_queued``
is set, and after commit the apply_projectuser_ad_change task retries the change.
"""
import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django_q.tasks import async_task
from ldap3.core.exceptions import LDAPBindError, LDAPCommunicationError

from coldfront.core.project.exceptions import ProjectUserStatusChangeError
from coldfront.core.project.models import ProjectUser, ProjectUserStatusChoice
from coldfront.core.project.utils import (
    deactivate_secondary_projectusers,
    reactivate_group_projectusers,
    reactivate_storage_allocationusers,
)
from coldfront.core.utils.common import import_from_settings
from coldfront.plugins.ldap.utils import LDAPConn

logger = logging.getLogger(__name__)

ADD = 'add'
REMOVE = 'remove'
DEACTIVATE = 'deactivate'
REACTIVATE = 'reactivate'

REMOVAL_STATUS = {REMOVE: 'Removed', DEACTIVATE: 'Deactivated'}

PENDING_STATUS = {
    ADD: 'Pending - Add',
    REACTIVATE: 'Pending - Add',
    REMOVE: 'Pending - Remove',
    DEACTIVATE: 'Pending - Remove',
}

# errors that mean AD could not be reached, rather than that it rejected the change
UNREACHABLE_ERRORS = (LDAPCommunicationError, LDAPBindError, OSError)

TASK_NAME = 'coldfront.plugins.ldap.tasks.apply_projectuser_ad_change'


def ad_sync_enabled():
    return import_from_settings('LDAP_PROJECTUSER_AD_SYNC', True)


def intent_for_change(old_status, new_status):
    """The AD intent for a ProjectUser status change, or None if it needs no AD write"""
    if old_status == new_status:
        return None
    if new_status == 'Active':
        return REACTIVATE if old_status == 'Deactivated' else ADD
    if new_status == 'Removed' and old_status is not None:
        # a row created as Removed was never a member, so there is nothing to remove
        return REMOVE
    return None


def apply_ad_intent(username, group_name, intent, actor_username=None, actor_role=None):
    """Make the AD change for intent and return the intent actually applied. For a removal that
    is DEACTIVATE if group_name is the user's primary group, otherwise REMOVE, regardless of
    which was asked for. Raises on rejection or when AD is unreachable.
    """
    ldap_conn = LDAPConn()
    if intent == ADD:
        ldap_conn.add_user_to_group(username, group_name)
    elif intent == REACTIVATE:
        ldap_conn.reactivate_user(username, actor_username=actor_username, actor_role=actor_role)
    else:
        intent = DEACTIVATE if ldap_conn.is_primary_group(username, group_name) else REMOVE
        ldap_conn.remove_member_from_group(
            username, group_name, actor_username=actor_username, actor_role=actor_role
        )
    return intent


def reactivate_user_groups(user):
    """Reactivate the user's ProjectUsers in the other AD groups they still belong to"""
    try:
        ldap_user = LDAPConn().return_user_by_name(user.username)
    except Exception as e:
        logger.warning(
            'Could not read AD groups of reactivated user; the daily sync will reactivate them.',
            extra={'category': 'ldap:User', 'status': 'failure', 'user': user.username, 'error': str(e)}
        )
        return
    group_names = [group.split(',')[0].replace('CN=', '') for group in ldap_user['memberOf']]
    reactivate_group_projectusers(user, group_names)


def complete_queued_change(projectuser, intent, complete_removal=False):
    """Follow-on changes for a queued AD change that has now succeeded. The in-request
    path does these in the view (or, for the group reactivation, in post_save).
    intent is the intent AD actually applied.
    """
    if intent == REACTIVATE:
        reactivate_user_groups(projectuser.user)
        reactivate_storage_allocationusers(projectuser.user)
    elif intent in REMOVAL_STATUS and complete_removal:
        # imported here: the view module is heavy and imports plugins of its own
        from coldfront.core.project.views import ProjectRemoveUsersView

        _, failed = ProjectRemoveUsersView().complete_removal(
            projectuser.project, projectuser.user, deactivated=intent == DEACTIVATE
        )
        for failure in failed:
            logger.error(
                'Queued removal follow-up failed.',
                extra={
                    'category': 'integration:AD',
                    'status': 'failure',
                    'user': projectuser.user.username,
                    'project': projectuser.project.title,
                    'error': failure,
                }
            )
    elif intent == DEACTIVATE:
        deactivate_secondary_projectusers(projectuser.user, projectuser.project)


@receiver(pre_save, sender=ProjectUser)
def projectuser_ad_pre_save(sender, instance, raw=False, **kwargs):
    """Make the AD change for a ProjectUser status change before the row is saved"""
    instance._ad_queued = None
    instance._ad_applied = None
    if raw or getattr(instance, '_skip_ad_sync', False) or not ad_sync_enabled():
        return
    old_status = None
    if instance.pk:
        old_status = ProjectUser.objects.filter(pk=instance.pk).values_list('status__name', flat=True).first()
    new_status = instance.status.name
    if old_status == new_status:
        return
    intent = getattr(instance, '_ad_intent', None) or intent_for_change(old_status, new_status)
    if intent is None:
        return
    actor_username, actor_role = getattr(instance, '_ad_actor', (None, None))
    log_extra = {
        'category': 'integration:AD',
        'user': instance.user.username,
        'project': instance.project.title,
        'intent': intent,
        'actor': actor_username,
    }
    try:
        applied = apply_ad_intent(instance.user.username, instance.project.title, intent, actor_username, actor_role)
    except UNREACHABLE_ERRORS as e:
        logger.warning(
            'AD unreachable; queueing ProjectUser AD change.',
            extra={**log_extra, 'status': 'queued', 'error': str(e)}
        )
        instance._ad_queued = {
            'intent': intent,
            'previous_status': old_status,
            'target_status': new_status,
            'actor_username': actor_username,
            'actor_role': actor_role,
            'complete_removal': bool(getattr(instance, '_ad_complete_removal', False)),
        }
        instance.status = ProjectUserStatusChoice.objects.get(name=PENDING_STATUS[intent])
        return
    except ProjectUserStatusChangeError:
        logger.warning('AD rejected ProjectUser change.', extra={**log_extra, 'status': 'failure'})
        raise
    except Exception as e:
        logger.warning('AD rejected ProjectUser change.', extra={**log_extra, 'status': 'failure', 'error': str(e)})
        raise ProjectUserStatusChangeError(
            f'AD rejected the change for {instance.user.username} in {instance.project.title}: {e}'
        ) from e
    if applied in REMOVAL_STATUS and applied != intent:
        # AD's primary group differs from what the caller expected; record what AD did
        logger.info(
            'AD applied a different removal than requested.',
            extra={**log_extra, 'status': 'success', 'applied': applied}
        )
        instance.status = ProjectUserStatusChoice.objects.get(name=REMOVAL_STATUS[applied])
    logger.info('Applied ProjectUser change to AD.', extra={**log_extra, 'status': 'success'})
    instance._ad_applied = applied


@receiver(post_save, sender=ProjectUser)
def projectuser_ad_post_save(sender, instance, raw=False, **kwargs):
    """Once the row is committed, queue the retry task, or cascade an applied reactivation or
    deactivation to the user's other projects"""
    if raw:
        return
    queued = getattr(instance, '_ad_queued', None)
    if queued:
        pk = instance.pk
        transaction.on_commit(lambda: async_task(TASK_NAME, pk, **queued))
    elif getattr(instance, '_ad_applied', None) == REACTIVATE:
        user = instance.user
        transaction.on_commit(lambda: reactivate_user_groups(user))
    elif getattr(instance, '_ad_applied', None) == DEACTIVATE and not getattr(instance, '_ad_complete_removal', False):
        # e.g. an admin edit that turned out to be the user's primary group; the remove view
        # does this cascade itself in complete_removal
        user, project = instance.user, instance.project
        transaction.on_commit(lambda: deactivate_secondary_projectusers(user, project))
