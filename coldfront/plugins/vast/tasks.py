from django.core.management import call_command

def sync_vast_allocations(resource_name=None):
    """Sync VAST userquotas into ColdFront allocations
    """
    if resource_name:
        call_command('sync_vast_allocations', resource=resource_name)
    else:
        call_command('sync_vast_allocations')
