from django.core.management.base import BaseCommand
from coldfront.plugins.sftocf.utils import pull_sf_push_cf_redash

class Command(BaseCommand):
    '''
    Collect usage data from Starfish and insert it into the Coldfront database.
    '''

    def handle(self, *args, **kwargs):

        '''
        Query Starfish Redash API for user usage data and update Coldfront AllocationUser entries.

        Only Projects that are already in Coldfront will get updated.

        Assumptions this code relies on:
        1. A project cannot have multiple allocations on the same storage resource.
        '''
        pull_sf_push_cf_redash()