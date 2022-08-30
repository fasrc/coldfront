from coldfront.plugins.fasrc.utils import AllTheThingsConn

def import_quotas(volumes=None):
    attconn = AllTheThingsConn()
    result_file = attconn.pull_quota_data(volumes=volumes)
    attconn.push_quota_data(result_file)
