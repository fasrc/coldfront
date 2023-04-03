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
