from coldfront.config.base import INSTALLED_APPS
from coldfront.config.env import ENV
from coldfront.config.logging import LOGGING

INSTALLED_APPS += [
    'coldfront.plugins.slurm',
]

SLURM_SACCTMGR_PATH = ENV.str('SLURM_SACCTMGR_PATH', default='/usr/bin/sacctmgr')
SLURM_NOOP = ENV.bool('SLURM_NOOP', False)
SLURM_IGNORE_USERS = ENV.list('SLURM_IGNORE_USERS', default=['root'])
SLURM_IGNORE_ACCOUNTS = ENV.list('SLURM_IGNORE_ACCOUNTS', default=[])

CLUSTERS = {}
for cluster in ENV.str('SLURM_CLUSTERS', '').split(','):
    cluster_name = f"SLURM_{cluster.upper()}"
    cluster_type = ENV.str(f"{cluster_name}_TYPE")
    if cluster_type =='cli':
        CLUSTERS[cluster] = {
            'name': cluster,
            'type': 'cli',
        }
    else:
        CLUSTERS[cluster] = {
            'name': cluster,
            'type': 'api',
            'base_url': ENV.str(f"{cluster_name}_ENDPOINT"),
            'user_token': ENV.str(f"{cluster_name}_USER_TOKEN"),
        }

LOGGING['handlers']['slurm'] = {
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': 'logs/slurm.log',
            'when': 'D',
            'backupCount': 10, # how many backup files to keep
            'formatter': 'default',
            'level': 'DEBUG',
        }

LOGGING['loggers']['coldfront.plugins.slurm'] = {
            'handlers': ['slurm'],
        }
