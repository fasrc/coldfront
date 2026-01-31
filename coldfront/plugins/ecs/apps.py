from django.apps import AppConfig


class SlurmConfig(AppConfig):
    name = 'coldfront.plugins.ecs'


    def ready(self):
        import coldfront.plugins.ecs.signals
