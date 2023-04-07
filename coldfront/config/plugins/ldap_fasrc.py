from django.core.exceptions import ImproperlyConfigured

from coldfront.config.env import ENV
from coldfront.config.base import INSTALLED_APPS

try:
    import ldap
    from django_auth_ldap.config import GroupOfNamesType, LDAPSearch
except ImportError:
    raise ImproperlyConfigured('Please run: pip install ldap3')

#------------------------------------------------------------------------------
# This enables searching for users via LDAP
#------------------------------------------------------------------------------


INSTALLED_APPS += [ 'coldfront.plugins.ldap' ]

AUTH_LDAP_SERVER_URI = ENV.str('AUTH_LDAP_SERVER_URI')
AUTH_LDAP_BIND_DN = ENV.str('AUTH_LDAP_BIND_DN')
AUTH_LDAP_BIND_PASSWORD = ENV.str('AUTH_LDAP_BIND_PASSWORD')
AUTH_LDAP_USER_SEARCH_BASE = ENV.str('AUTH_LDAP_USER_SEARCH_BASE')
AUTH_LDAP_GROUP_SEARCH_BASE = ENV.str('AUTH_LDAP_GROUP_SEARCH_BASE')
