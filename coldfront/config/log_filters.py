import logging
from ipware import get_client_ip
from threading import local

_thread_locals = local()

def get_current_request():
    return getattr(_thread_locals, "request", None)

class RequestMiddleware:
    """
    Middleware that saves the request object in thread local storage.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_locals.request = request
        response = self.get_response(request)
        return response

class RequestFilter(logging.Filter):
    """
    Logging filter that adds `ip_addr` from the request (if available).
    """
    def filter(self, record):
        request = get_current_request()
        if request is not None:
            ip, _ = get_client_ip(request)
            if not hasattr(record, 'ip_addr'):
                record.ip_addr = ip or ''

            request_user = getattr(request, "user", None)
            if request_user and request_user.is_authenticated:
                request_username = getattr(
                    request_user, "get_username", lambda: str(request_user)
                )()
            else:
                request_username = 'anonymous'
            if not hasattr(record, 'requesting_user'):
                record.requesting_user = request_username

            if not hasattr(record, 'auth_backend'):
                record.auth_backend = request.session._session_cache.get(
                    '_auth_user_backend', 'unknown'
                )
        else:
            if not hasattr(record, 'ip_addr'):
                record.ip_addr = ''
            if not hasattr(record, 'requesting_user'):
                record.requesting_user = ''
            if not hasattr(record, 'auth_backend'):
                record.auth_backend = ''
        if not hasattr(record, 'category'):
            record.category = ''
        return True
