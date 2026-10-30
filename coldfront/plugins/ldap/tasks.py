import logging
from datetime import timedelta

from django.core.management import call_command
from django.utils import timezone
from django_q.models import Schedule
from django_q.tasks import schedule

from coldfront.core.project.models import ProjectUser, ProjectUserStatusChoice
from coldfront.core.utils.common import import_from_settings
from coldfront.core.utils.mail import send_email
from coldfront.plugins.ldap.projectuser_sync import (
    PENDING_STATUS,
    TASK_NAME,
    UNREACHABLE_ERRORS,
    apply_ad_intent,
    complete_queued_change,
)
from coldfront.plugins.ldap.utils import collect_update_project_status_membership

logger = logging.getLogger(__name__)

SCHEDULED_TASKS = [
    {'name': 'update_group_membership_ldap', 'schedule_type': Schedule.DAILY},
    {'name': 'id_add_projects', 'schedule_type': Schedule.DAILY},
]

def update_group_membership_ldap():
    """Update ProjectUsers for active Projects using ADGroup and ADUser data
    """
    collect_update_project_status_membership()

def id_add_projects():
    """ID and add new projects from ADGroup and ADUser data
    """
    call_command('id_add_new_projects')


def apply_projectuser_ad_change(
    projectuser_pk, intent, previous_status, target_status,
    actor_username=None, actor_role=None, attempt=1, complete_removal=False,
):
    """Retry a ProjectUser AD change that was queued because AD was unreachable.

    On success the ProjectUser gets target_status. If complete_removal is set, the remove view's follow-ups (allocations, Slurm, emails) run then.
    While AD stays unreachable the task reschedules itself every LDAP_PROJECTUSER_RETRY_MINUTES, up to LDAP_PROJECTUSER_MAX_ATTEMPTS
    attempts (django-q does not retry tasks that raise). If AD rejects the change or the attempts
    run out, the ProjectUser is reverted to previous_status and EMAIL_ADMIN_LIST is emailed.
    """
    try:
        projectuser = ProjectUser.objects.select_related('user', 'project', 'status').get(pk=projectuser_pk)
    except ProjectUser.DoesNotExist:
        logger.warning('Queued AD change for missing ProjectUser %s; skipping.', projectuser_pk)
        return
    log_extra = {
        'category': 'integration:AD',
        'user': projectuser.user.username,
        'project': projectuser.project.title,
        'intent': intent,
        'attempt': attempt,
    }
    if projectuser.status.name != PENDING_STATUS[intent]:
        logger.info(
            'ProjectUser changed while its AD change was queued; skipping.',
            extra={**log_extra, 'status': 'superseded', 'current_status': projectuser.status.name}
        )
        return

    try:
        apply_ad_intent(
            projectuser.user.username, projectuser.project.title, intent, actor_username, actor_role
        )
    except UNREACHABLE_ERRORS as e:
        max_attempts = import_from_settings('LDAP_PROJECTUSER_MAX_ATTEMPTS', 36)
        if attempt < max_attempts:
            retry_minutes = import_from_settings('LDAP_PROJECTUSER_RETRY_MINUTES', 10)
            logger.warning(
                'AD still unreachable; rescheduling ProjectUser AD change.',
                extra={**log_extra, 'status': 'queued', 'error': str(e)}
            )
            schedule(
                TASK_NAME, projectuser_pk, intent, previous_status, target_status,
                actor_username, actor_role, attempt + 1,
                complete_removal=complete_removal,
                schedule_type=Schedule.ONCE,
                next_run=timezone.now() + timedelta(minutes=retry_minutes),
            )
            return
        revert_projectuser(projectuser, previous_status, intent, f'AD unreachable after {attempt} attempts: {e}')
        return
    except Exception as e:
        revert_projectuser(projectuser, previous_status, intent, f'AD rejected the change: {e}')
        return

    projectuser.status = ProjectUserStatusChoice.objects.get(name=target_status)
    projectuser._skip_ad_sync = True
    projectuser.save()
    complete_queued_change(projectuser, intent, complete_removal)
    logger.info('Applied queued ProjectUser change to AD.', extra={**log_extra, 'status': 'success'})


def revert_projectuser(projectuser, previous_status, intent, error):
    """Put a ProjectUser whose queued AD change failed back to its previous status, and
    email EMAIL_ADMIN_LIST. A row that was new when the change was queued is set to Removed.
    """
    pending_status = projectuser.status.name
    reverted_status = previous_status or 'Removed'
    projectuser.status = ProjectUserStatusChoice.objects.get(name=reverted_status)
    projectuser._skip_ad_sync = True
    projectuser.save()
    logger.error(
        'Queued ProjectUser AD change failed; reverted.',
        extra={
            'category': 'integration:AD',
            'status': 'failure',
            'user': projectuser.user.username,
            'project': projectuser.project.title,
            'intent': intent,
            'reverted_to': reverted_status,
            'error': error,
        }
    )
    receivers = import_from_settings('EMAIL_ADMIN_LIST', [])
    if not receivers:
        logger.error('EMAIL_ADMIN_LIST not set; not emailing failed AD change for %s', projectuser)
        return
    body = (
        f'A queued AD change for ProjectUser {projectuser.user.username} in project '
        f'{projectuser.project.title} failed and was reverted.\n\n'
        f'Intended change: {intent}\n'
        f'Status: {pending_status} -> {reverted_status}\n'
        f'Error: {error}\n\n'
        'Any allocation changes or emails made when the change was requested were not undone '
        '(removals made from the project page wait for AD, so they have none).\n'
    )
    try:
        send_email(
            f'AD change failed for {projectuser.user.username} in {projectuser.project.title}',
            body,
            import_from_settings('EMAIL_SENDER'),
            receivers,
        )
    except Exception as e:
        logger.exception('Error emailing failed AD change for %s: %s', projectuser, e)
