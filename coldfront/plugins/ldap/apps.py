from django.apps import AppConfig


class LdapConfig(AppConfig):
    name = 'coldfront.plugins.ldap'


    def ready(self):
        import coldfront.plugins.ldap.signals
        import coldfront.plugins.ldap.projectuser_sync  # noqa: F401  registers ProjectUser AD receivers
