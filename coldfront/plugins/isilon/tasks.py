from django.core import management

def pull_isilon_quotas():
    """Pull Isilon quotas
    """
    management.call_command('pull_isilon_quotas')
