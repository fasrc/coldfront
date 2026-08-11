from django.core.management import call_command
from django_q.models import Schedule

SCHEDULED_TASKS = [
    {'name': 'xdmod_usage', 'schedule_type': Schedule.DAILY},
]

def xdmod_usage():
    """Add xdmod usage data
    """
    call_command('xdmod_usage', sync=True)
