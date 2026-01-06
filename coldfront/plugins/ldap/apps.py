from django.apps import AppConfig


class LdapConfig(AppConfig):
    name = 'coldfront.plugins.ldap'


    def ready(self):
        import coldfront.plugins.ldap.signals
