import logging
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

log = logging.getLogger(__name__)

@receiver(user_logged_in)
def user_logged_in_callback(sender, request, user, **kwargs):    
    log.info('successful user login', extra={
        'user': {
            'id': user.id,
            'username': user.get_username(),
        },
    })

@receiver(user_logged_out)
def user_logged_out_callback(sender, request, user, **kwargs): 
    log.info('successful user logout', extra={
        'user': {
            'id': user.id,
            'username': user.get_username(),
        },
    })

@receiver(user_login_failed)
def user_login_failed_callback(sender, credentials, **kwargs):
    log.warning('failed user login', extra={
            'credentials': credentials
        }
    )
