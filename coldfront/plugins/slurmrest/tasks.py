from django.core.management import call_command

def slurmrest_sync():
    """ID and add new slurm allocations from ADGroup and ADUser data
    """
    call_command('slurmrest_sync')
