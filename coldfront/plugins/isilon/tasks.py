from django.core import management

def sync_isilon_allocations(resource_name=None):
    """Sync Isilon/PowerScale directory smartquotas into ColdFront allocations
    """
    if resource_name:
        reports = management.call_command('sync_isilon_allocations', resource=resource_name)
    else:
        reports = management.call_command('sync_isilon_allocations')
    return reports
