from django.apps import AppConfig

from coldfront.core.utils.common import import_from_settings


class FASRCConfig(AppConfig):
    name = 'coldfront.plugins.fasrc'

    def ready(self):
        import coldfront.plugins.fasrc.signals  # noqa: F401
