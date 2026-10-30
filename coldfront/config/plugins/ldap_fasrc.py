"""
FASRC-specific LDAP plugin settings
"""
import sys

from django.core.exceptions import ImproperlyConfigured

from coldfront.config.env import ENV
from coldfront.config.logging import LOGGING
from coldfront.config.base import INSTALLED_APPS

try:
    import ldap3
    from django_auth_ldap.config import GroupOfNamesType, LDAPSearch
except ImportError as exc:
    raise ImproperlyConfigured('Please run: pip install ldap3') from exc

INSTALLED_APPS += [ 'coldfront.plugins.ldap' ]

AUTH_LDAP_SERVER_URI = ENV.str('AUTH_LDAP_SERVER_URI')
AUTH_LDAP_BIND_DN = ENV.str('AUTH_LDAP_BIND_DN')
AUTH_LDAP_BIND_PASSWORD = ENV.str('AUTH_LDAP_BIND_PASSWORD')
AUTH_LDAP_USER_SEARCH_BASE = ENV.str('AUTH_LDAP_USER_SEARCH_BASE')
AUTH_LDAP_GROUP_SEARCH_BASE = ENV.str('AUTH_LDAP_GROUP_SEARCH_BASE')
CF_LDAP_PROJECT_GROUP_SAM = ENV.str('CF_LDAP_PROJECT_GROUP_SAM', default=None)
CF_LDAP_FASSE_GROUP = ENV.str('CF_LDAP_FASSE_GROUP', default=None)

# ProjectUser status changes are written to AD from pre_save; when AD is unreachable the change
# is queued and retried every LDAP_PROJECTUSER_RETRY_MINUTES, up to LDAP_PROJECTUSER_MAX_ATTEMPTS times.
# Off during test runs so ProjectUser saves in tests never write to a real AD; tests of the
# sync turn it on with override_settings and mock LDAPConn.
TESTING = 'test' in sys.argv or 'test_coverage' in sys.argv
LDAP_PROJECTUSER_AD_SYNC = not TESTING and ENV.bool('LDAP_PROJECTUSER_AD_SYNC', default=True)
LDAP_PROJECTUSER_RETRY_MINUTES = ENV.int('LDAP_PROJECTUSER_RETRY_MINUTES', default=10)
LDAP_PROJECTUSER_MAX_ATTEMPTS = ENV.int('LDAP_PROJECTUSER_MAX_ATTEMPTS', default=36)


LOGGING['handlers']['ldap_fasrc'] = {
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': 'logs/ldap_fasrc.log',
            'backupCount': 10,
            'when': 'midnight',
            'formatter': 'default',
            'level': 'DEBUG',
        }

LOGGING['loggers']['coldfront.plugins.ldap'] = {
            'handlers': ['ldap_fasrc'],
        }
