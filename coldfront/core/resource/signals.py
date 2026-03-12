import django.dispatch

resource_apicluster_table_data_request = django.dispatch.Signal()
# [resource, allocations]

resource_clicluster_table_data_request = django.dispatch.Signal()
# [resource, allocations]

update_volume_information = django.dispatch.Signal()
