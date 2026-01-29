from django.apps import AppConfig


class SlurmConfig(AppConfig):
    name = 'coldfront.plugins.isilon'


    def ready(self):
        import coldfront.plugins.isilon.signals
