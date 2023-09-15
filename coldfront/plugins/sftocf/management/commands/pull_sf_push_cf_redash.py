from django.core.management.base import BaseCommand
from coldfront.plugins.sftocf.utils import RedashDataPipeline

class Command(BaseCommand):
    """
    Collect usage data from Starfish and insert it into the Coldfront database.
    """

    def handle(self, *args, **kwargs):
        """
        Query Starfish Redash API for user usage data and update Coldfront AllocationUser entries.

        Only Projects that are already in Coldfront will get updated.
        """

        data_pull = RedashDataPipeline()

        allocationquerymatch_objs, user_models = data_pull.clean_collected_data()
        data_pull.update_coldfront_objects(allocationquerymatch_objs, user_models)
