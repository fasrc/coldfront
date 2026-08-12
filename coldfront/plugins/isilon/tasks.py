from django.core import management
from django_q.models import Schedule

# pull_isilon_quotas is superseded by sync_isilon_allocations and intentionally
# not scheduled here.
SCHEDULED_TASKS = [
    {'name': 'sync_isilon_allocations', 'schedule_type': Schedule.DAILY, 'time': '02:00'},
]

def sync_isilon_allocations(resource_name=None):
    """Sync Isilon/PowerScale directory smartquotas into ColdFront allocations
    """
    if resource_name:
        management.call_command('sync_isilon_allocations', resource=resource_name)
    else:
        management.call_command('sync_isilon_allocations')
