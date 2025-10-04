from coldfront.config.base import INSTALLED_APPS
from coldfront.config.env import ENV  # noqa: F401
from coldfront.config.logging import LOGGING


if "slurmrest" not in INSTALLED_APPS:
    INSTALLED_APPS += [
        "coldfront.plugins.slurmrest",
    ]

SLURMREST_CLUSTER_ATTRIBUTE_NAME = ENV.str("SLURMREST_CLUSTER_ATTRIBUTE_NAME", default="slurm_cluster")
SLURMREST_ACCOUNT_ATTRIBUTE_NAME = ENV.str(
        "SLURMREST_ACCOUNT_ATTRIBUTE_NAME", default="slurm_account_name")
SLURMREST_SPECS_ATTRIBUTE_NAME = ENV.str(
        "SLURMREST_SPECS_ATTRIBUTE_NAME", default="slurm_specs")
SLURMREST_USER_SPECS_ATTRIBUTE_NAME = ENV.str(
        "SLURMREST_USER_SPECS_ATTRIBUTE_NAME", default="slurm_user_specs")

SLURMREST_NOOP = ENV.bool('SLURMREST_NOOP', default=False)
SLURMREST_IGNORE_USERS = ENV.list('SLURMREST_IGNORE_USERS', default=['root'])
SLURMREST_IGNORE_ACCOUNTS = ENV.list('SLURMREST_IGNORE_ACCOUNTS', default=[])
SLURMREST_IGNORE_CLUSTERS = ENV.list('SLURMREST_IGNORE_CLUSTERS', default=[])

SLURMREST_CLUSTERS = {}
for cluster in ENV.str('SLURMREST_CLUSTERS', '').split(','):
    cluster_envname = f"SLURMREST_{cluster.upper()}"
    SLURMREST_CLUSTERS[cluster] = {
        'name': cluster,
        'base_url': ENV.str(f"{cluster_envname}_ENDPOINT"),
        'token': ENV.str(f"{cluster_envname}_TOKEN"),
    }


LOGGING['handlers']['slurmrest'] = {
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': 'logs/slurmrest.log',
            'when': 'D',
            'backupCount': 10, # how many backup files to keep
            'formatter': 'default',
            'level': 'DEBUG',
        }

LOGGING['loggers']['coldfront.plugins.slurmrest'] = {
            'handlers': ['slurmrest'],
        }
