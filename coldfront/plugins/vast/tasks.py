from django.core.management import call_command
from django_q.models import Schedule

SCHEDULED_TASKS = [
    {'name': 'sync_vast_allocations', 'schedule_type': Schedule.DAILY, 'time': '02:15'},
]

def sync_vast_allocations(resource_name=None):
    """Sync VAST userquotas into ColdFront allocations
    """
    if resource_name:
        call_command('sync_vast_allocations', resource=resource_name)
    else:
        call_command('sync_vast_allocations')
