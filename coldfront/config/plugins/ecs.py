from coldfront.config.env import ENV
from coldfront.config.logging import LOGGING
from coldfront.config.base import INSTALLED_APPS

INSTALLED_APPS += [ 'coldfront.plugins.ecs' ]
ECS_USER = ENV.str('ECS_USER', '')
ECS_PASS = ENV.str('ECS_PASS', '')

LOGGING['handlers']['ecs'] = {
    'class': 'logging.handlers.TimedRotatingFileHandler',
    'filename': 'logs/ecs.log',
    'when': 'D',
    'backupCount': 10, # how many backup files to keep
    'formatter': 'default',
    'level': 'DEBUG',
}

LOGGING['loggers']['coldfront.plugins.ecs'] = {
    'handlers': ['ecs'],
}
