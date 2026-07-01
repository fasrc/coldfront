from coldfront.config.base import INSTALLED_APPS

INSTALLED_APPS += ["coldfront_notifications"]

EXTRA_APPS_URLS = [
    ("notifications/", "coldfront_notifications.urls", "notifications"),
]
