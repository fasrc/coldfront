from django.apps import AppConfig


class SlurmConfig(AppConfig):
    name = 'coldfront.plugins.slurmrest'


    def ready(self):
        import coldfront.plugins.slurmrest.signals
