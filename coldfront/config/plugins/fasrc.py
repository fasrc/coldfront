from coldfront.config.env import ENV
from coldfront.config.logging import LOGGING
from coldfront.config.base import INSTALLED_APPS


INSTALLED_APPS += [ 'coldfront.plugins.fasrc' ]

NEO4JP = ENV.str('NEO4JP')

LOGGING['formatters']['fasrc'] = {
            "()": "django.utils.log.ServerFormatter",
            "format": "[{server_time}] {message}",
            "style": "{",
        }

LOGGING['handlers']['fasrc'] = {
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': 'logs/fasrc.log',
            'backupCount': 10,
            'when': 'midnight',
            'formatter': 'fasrc',
            'level': 'DEBUG',
        }

LOGGING['handlers']['import_quotas'] = {
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': 'logs/import_quotas.log',
            'backupCount': 10,
            'when': 'midnight',
            'formatter': 'fasrc',
            'level': 'DEBUG',
        }

LOGGING['handlers']['add_allocations'] = {
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': 'logs/add_allocations.log',
            'backupCount': 10,
            'when': 'midnight',
            'formatter': 'fasrc',
            'level': 'DEBUG',
        }

LOGGING['loggers']['coldfront.plugins.fasrc'] = {
            'handlers': ['fasrc', 'key-events'],
        }

LOGGING['loggers']['import_quotas'] = {
            'handlers': ['import_quotas', 'key-events'],
        }

LOGGING['loggers']['coldfront.plugins.fasrc.management.commands.id_import_new_allocations'] = {
            'handlers': ['add_allocations', 'key-events'],
        }
