from django.core.management import call_command
from django_q.models import Schedule

from coldfront.plugins.ldap.utils import collect_update_project_status_membership

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
