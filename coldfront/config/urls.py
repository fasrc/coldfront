"""
ColdFront URL Configuration
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView
from django.conf.urls.static import static


import coldfront.core.portal.views as portal_views

admin.site.site_header = 'ColdFront Administration'
admin.site.site_title = 'ColdFront Administration'

urlpatterns = static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) + [
    path('admin/', admin.site.urls),
    path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain'), name="robots"),
    path('', portal_views.home, name='home'),
    path('center-summary', portal_views.center_summary, name='center-summary'),
    path('help-page', portal_views.help_page, name='help-page'),
    path('allocation-summary', portal_views.allocation_summary, name='allocation-summary'),
    path('allocation-by-fos', portal_views.allocation_by_fos, name='allocation-by-fos'),
    path('user/', include('coldfront.core.user.urls')),
    # path('opt_out/', portal_views.opt_out, name='opt-out'),
    # path('__debug__/', include('debug_toolbar.urls')),
    path('project/', include('coldfront.core.project.urls')),
    path('allocation/', include('coldfront.core.allocation.urls')),
    path('resource/', include('coldfront.core.resource.urls')),
    path('grant/', include('coldfront.core.grant.urls')),
    path('department/', include('coldfront.core.department.urls')),
    path('publication/', include('coldfront.core.publication.urls')),
    path('research-output/', include('coldfront.core.research_output.urls')),
]


if 'coldfront.plugins.iquota' in settings.INSTALLED_APPS:
    urlpatterns.append(path('iquota/', include('coldfront.plugins.iquota.urls')))

if 'mozilla_django_oidc' in settings.INSTALLED_APPS:
    urlpatterns.append(path('oidc/', include('mozilla_django_oidc.urls')))

if 'django_su.backends.SuBackend' in settings.AUTHENTICATION_BACKENDS:
    urlpatterns.append(path('su/', include('django_su.urls')))

if 'coldfront.plugins.ifx' in settings.INSTALLED_APPS:
    urlpatterns.append(path('ifx/', include('coldfront.plugins.ifx.urls')))

if 'coldfront.plugins.api' in settings.INSTALLED_APPS:
    urlpatterns.append(path('api/', include('coldfront.plugins.api.urls')))

if 'coldfront.plugins.fasrc_monitoring' in settings.INSTALLED_APPS:
    urlpatterns.append(path('', include('coldfront.plugins.fasrc_monitoring.urls')))

if 'django_prometheus' in settings.INSTALLED_APPS:
    urlpatterns.append(path('', include('django_prometheus.urls')))
