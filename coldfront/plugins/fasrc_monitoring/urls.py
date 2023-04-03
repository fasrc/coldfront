from django.urls import path, include
from rest_framework import routers
from coldfront.plugins.fasrc_monitoring.views import monitor

router = routers.DefaultRouter()

urlpatterns = [
    path('monitor', monitor, name='monitor'),
]
