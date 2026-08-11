from django.core.management import call_command
from django_q.models import Schedule

SCHEDULED_TASKS = [
    {'name': 'slurmrest_sync', 'schedule_type': Schedule.DAILY},
]

def slurmrest_sync():
    """ID and add new slurm allocations from ADGroup and ADUser data
    """
    call_command('slurmrest_sync')
