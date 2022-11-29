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
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
        'django-q': {
            'class': 'logging.FileHandler',
            'filename': 'django-q.log',
        },
        # 'file': {
        #     'class': 'logging.FileHandler',
        #     'filename': '/tmp/debug.log',
        # },
    },
    'loggers': {
        'django_auth_ldap': {
            'level': 'INFO',
            # 'handlers': ['console', 'file'],
            'handlers': ['console', ],
        },
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'django-q': {
            'handlers': ['django-q'],
            'level': 'DEBUG',
        },
        '': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'ifx': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'ifxbilling': {
            'handlers': ['console'],
            'level': 'INFO',
        },
    },
}
