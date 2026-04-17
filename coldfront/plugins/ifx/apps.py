from functools import wraps

from django.apps import AppConfig
from django.conf import settings
from django.contrib.auth import get_user_model


class IfxConfig(AppConfig):
    default_auto_field = 'django.db.models.AutoField'
    name = 'coldfront.plugins.ifx'

    def ready(self):
        if 'django_su.backends.SuBackend' not in settings.AUTHENTICATION_BACKENDS:
            return
        try:
            from django_su import views as su_views
        except ImportError:
            return

        if getattr(su_views.login_as_user, '_su_logging_wrapped', False):
            return

        from coldfront.core.utils.common import log_su_impersonation

        _orig = su_views.login_as_user

        @wraps(_orig)
        def login_as_user_with_logging(request, user_id):
            actor = request.user
            response = _orig(request, user_id)
            if getattr(response, 'status_code', None) != 302:
                return response
            User = get_user_model()
            try:
                target = User.objects.get(pk=user_id)
            except (User.DoesNotExist, ValueError, TypeError):
                return response
            actor_pk = getattr(actor, 'pk', None)
            if actor_pk is not None and actor_pk != target.pk:
                log_su_impersonation(actor, target, source='su_login')
            return response

        login_as_user_with_logging._su_logging_wrapped = True
        su_views.login_as_user = login_as_user_with_logging
