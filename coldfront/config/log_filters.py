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
            record.ip_addr = ip or ''
            user = getattr(request, "user", None)
            if user and user.is_authenticated:
                record.user = getattr(user, "get_username", lambda: str(user))()
            else:
                record.user = 'anonymous'
        else:
            record.ip_addr = ''
            record.user = ''
        if not hasattr(record, 'category'):
            record.category = ''
        return True
