from coldfront.plugins.fasrc.utils import pull_push_quota_data
import logging

def import_quotas(volumes=None):
    '''
    Collect group-level quota and usage data from ATT and insert it into the
    Coldfront database.

    Parameters
    ----------
    volumes : string of volume names separated by commas. Optional, default None
    '''
    logger = logging.getLogger('import_quotas')
    if volumes:
        volumes = volumes.split(",")
    pull_push_quota_data()
