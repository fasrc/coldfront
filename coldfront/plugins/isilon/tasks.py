from django.core import management


def sync_isilon_allocations():
    """Sync isilon/powerscale allocation records with live cluster quota data."""
    management.call_command("sync_isilon_allocations")
