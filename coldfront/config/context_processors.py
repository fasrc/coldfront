import os

def export_vars(request):
    data = {}
    data['PLUGIN_FASRC_MONITORING'] = os.environ['PLUGIN_FASRC_MONITORING']
    return data
