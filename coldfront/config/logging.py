from django.contrib.messages import constants as messages

#------------------------------------------------------------------------------
# ColdFront logging config
#------------------------------------------------------------------------------

MESSAGE_TAGS = {
    messages.DEBUG: 'info',
    messages.INFO: 'info',
    messages.SUCCESS: 'success',
    messages.WARNING: 'warning',
    messages.ERROR: 'danger',
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue'
        },
        'request': {
            '()': 'coldfront.config.log_filters.RequestFilter',
        },
    },
    'formatters': {
        'key-events': {
            "()": "coldfront.config.log_formatters.LogfmtServerFormatter",
            "format": "[{server_time}] {name} {levelname} {message}",
            "style": "{",
        },
        'default': {
            "()": "coldfront.config.log_formatters.LogfmtServerFormatter",
            "format": "[{server_time}] {name} {levelname} {message}",
            "style": "{",
        },
        'json': {
            '()': "pythonjsonlogger.jsonlogger.JsonFormatter",
            'fmt': '%(asctime)s %(name)s %(levelname)s %(message)s %(ip_addr) %(user)',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'json',
            'level': 'INFO',
            'filters': ['request'],
        },
        'console_debug': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
            'level': 'DEBUG',
            'filters': ['require_debug_true'],
        },
        'django-q': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/django-q.log',
            'backupCount': 7,
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'formatter': 'key-events',
            'level': 'DEBUG',
        },
        'key-events': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/key-events.log',
            'backupCount': 7,
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'formatter': 'key-events',
            'level': 'INFO',
        },
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler',
        },
        'json': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/coldfront.json.log',
            'backupCount': 7,
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'formatter': 'json',
            'level': 'INFO',
            'filters': ['request'],
        },
        # 'file': {
        #     'class': 'logging.FileHandler',
        #     'filename': '/tmp/debug.log',
        # },
    },
    'loggers': {
        'coldfront': {
            'handlers': ['console', 'json'],
            'level': 'INFO',
        },
        'django': {
            'handlers': ['console', 'json'],
            'level': 'INFO',
        },
        'django_auth_ldap': {
            'level': 'INFO',
            # 'handlers': ['console', 'file'],
            'handlers': ['console'],
        },
        'django-q': {
            'handlers': ['console', 'django-q', 'json', 'key-events'],
        },
        'ifx': {
            'handlers': ['console', 'console_debug', 'json', 'key-events', 'mail_admins'],
            'level': 'INFO',
        },
        'ifxbilling': {
            'handlers': ['console', 'console_debug', 'json', 'mail_admins'],
            'level': 'INFO',
        },
        'request': {
            'handlers': ['console', 'json'],
            'level': 'INFO',
        }
    },
}
