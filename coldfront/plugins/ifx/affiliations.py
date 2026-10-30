'''
Report ProjectUser additions and removals to Nanites as organization affiliation changes.

A user is added when their ProjectUser status changes to Active (from any status but Deactivated)
and removed when it becomes Removed. After the transaction commits, each change is sent to
NANITES_AFFILIATION_URL as one {"ifxid", "ifxorg", "active"} entry per organization linked
to the project, and the response is logged. Removals are skipped for an organization when the
user still belongs to another project linked to it. If the project has no organization, the
IFX_MANAGER addresses are emailed instead.
'''
# pylint: disable=broad-exception-caught,logging-fstring-interpolation
import logging
from collections import defaultdict

import requests
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from coldfront.core.project.models import ProjectUser
from coldfront.core.project.signals import project_projectusers_status_change
from coldfront.core.utils.common import import_from_settings
from coldfront.plugins.ifx.models import email_ifx_managers

logger = logging.getLogger('ifx')

# ProjectUser statuses that do not count as belonging to a project for the removal check
NON_MEMBER_STATUSES = ['Removed', 'Denied', 'Pending - Add']


def classify_change(old_status, new_status):
    '''
    Return True if a ProjectUser status change is an addition, False if it is a removal,
    or None if it is neither. old_status is None for a newly created ProjectUser.
    Deactivated -> Active is a reactivation, not an addition.
    '''
    if old_status == new_status:
        return None
    if new_status == 'Active' and old_status != 'Deactivated':
        return True
    if new_status == 'Removed' and old_status is not None:
        return False
    return None


@receiver(pre_save, sender=ProjectUser)
def projectuser_pre_save(sender, instance, **kwargs):
    '''Record the stored status so post_save can tell what changed'''
    instance._previous_status_name = None
    if instance.pk and not kwargs.get('raw'):
        instance._previous_status_name = ProjectUser.objects.filter(
            pk=instance.pk
        ).values_list('status__name', flat=True).first()


@receiver(post_save, sender=ProjectUser)
def projectuser_post_save(sender, instance, created, **kwargs):
    '''Queue an affiliation update when a saved ProjectUser is added or removed'''
    if kwargs.get('raw'):
        return
    old_status = None if created else getattr(instance, '_previous_status_name', None)
    active = classify_change(old_status, instance.status.name)
    if active is not None:
        queue_affiliation_changes([(instance.user, instance.project, active)])


@receiver(project_projectusers_status_change)
def projectusers_status_change(sender, projectusers, new_status, created=False, **kwargs):
    '''Queue affiliation updates for bulk ProjectUser status changes that bypass post_save'''
    changes = []
    for projectuser in projectusers:
        old_status = None if created else projectuser.status.name
        active = classify_change(old_status, new_status)
        if active is not None:
            changes.append((projectuser.user, projectuser.project, active))
    if changes:
        queue_affiliation_changes(changes)


def queue_affiliation_changes(changes):
    '''
    Sync a list of (user, project, active) changes once the current transaction commits,
    so nothing is sent for changes that are rolled back
    '''
    transaction.on_commit(lambda: sync_affiliations(changes))


def sync_affiliations(changes):
    '''Send (user, project, active) changes to Nanites. Errors are logged, never raised.'''
    try:
        entries = build_affiliation_entries(changes)
        if entries:
            post_affiliations(entries)
    except Exception as e:
        logger.exception(f'Error syncing affiliation changes {changes}: {e}')


def project_ifxorgs(project):
    '''ifxorg values of the Organizations linked to a project'''
    return list(
        project.projectorganization_set.exclude(organization__ifxorg__isnull=True)
        .exclude(organization__ifxorg='')
        .values_list('organization__ifxorg', flat=True)
        .distinct()
    )


def belongs_to_other_org_project(user, project, ifxorg):
    '''True if the user belongs to a project other than this one that is linked to ifxorg'''
    return ProjectUser.objects.filter(
        user=user,
        project__projectorganization__organization__ifxorg=ifxorg,
    ).exclude(project=project).exclude(status__name__in=NON_MEMBER_STATUSES).exists()


def build_affiliation_entries(changes):
    '''
    Turn (user, project, active) changes into Nanites affiliation entries, emailing the
    IFX_MANAGER addresses about changes to projects that have no organization
    '''
    entries = []
    unlinked = defaultdict(list)
    for user, project, active in changes:
        ifxorgs = project_ifxorgs(project)
        if not ifxorgs:
            unlinked[project].append((user, active))
            continue
        if not user.ifxid:
            logger.error(f'User {user.username} has no ifxid; not sending affiliation change for {project.title}')
            continue
        if not active:
            ifxorgs = [ifxorg for ifxorg in ifxorgs if not belongs_to_other_org_project(user, project, ifxorg)]
        for ifxorg in ifxorgs:
            entry = {'ifxid': user.ifxid, 'ifxorg': ifxorg, 'active': active}
            if entry not in entries:
                entries.append(entry)

    for project, project_changes in unlinked.items():
        send_unlinked_project_email(project, project_changes)
    return entries


def send_unlinked_project_email(project, project_changes):
    '''Tell the IFX_MANAGER addresses that users were added to or removed from a project with no organization'''
    lines = [
        f'User {user.username} with ifxuser id {user.ifxid} was {"added to" if active else "removed from"} the project.'
        for user, active in project_changes
    ]
    subject = f'Could not identify an organization for project {project.title}'
    body = (
        f'An organization could not be identified for project {project.title}, '
        'so these changes were not sent to Nanites:\n\n' + '\n'.join(lines) + '\n'
    )
    email_ifx_managers(subject, body, f'missing organization notice for project {project.title}')


def post_affiliations(entries):
    '''POST affiliation entries to NANITES_AFFILIATION_URL and log the response'''
    url = import_from_settings('NANITES_AFFILIATION_URL', None)
    if not url:
        logger.info(f'NANITES_AFFILIATION_URL not set; not sending affiliation updates {entries}')
        return
    token = import_from_settings('IFX_APP', {}).get('token')
    timeout = import_from_settings('NANITES_AFFILIATION_TIMEOUT', 30)
    try:
        response = requests.post(url, json=entries, headers={'Authorization': f'Token {token}'}, timeout=timeout)
        response.raise_for_status()
        results = response.json()
    except (requests.RequestException, ValueError) as e:
        logger.error(f'Error sending affiliation updates {entries} to Nanites: {e}')
        return

    if not isinstance(results, list):
        logger.error(f'Unexpected Nanites affiliation response for {entries}: {results}')
        return
    for result in results:
        if not isinstance(result, dict):
            logger.error(f'Unexpected Nanites affiliation response entry: {result}')
            continue
        logger.info(
            f'Nanites affiliation response for ifxid {result.get("ifxid")}, '
            f'ifxorg {result.get("ifxorg")}: {result.get("message")}'
        )
