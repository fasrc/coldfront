from django.core import management

def pull_isilon_quotas():
    """Pull Isilon quotas
    """
    management.call_command('pull_isilon_quotas')

def sync_isilon_allocations(resource_name=None):
    """Sync Isilon/PowerScale directory smartquotas into ColdFront allocations
    """
    if resource_name:
        management.call_command('sync_isilon_allocations', resource=resource_name)
    else:
        management.call_command('sync_isilon_allocations')
