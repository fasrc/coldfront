import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_save
from django.dispatch import receiver

from coldfront.core.user.models import UserProfile

log = logging.getLogger(__name__)

@receiver(post_save, sender=get_user_model())
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=get_user_model())
def save_user_profile(sender, instance, **kwargs):
    instance.userprofile.save()


@receiver(user_logged_in)
def user_logged_in_callback(sender, request, user, **kwargs):
    log.info('successful user login', extra={'category': 'auth', 'status': 'success'})

@receiver(user_logged_out)
def user_logged_out_callback(sender, request, user, **kwargs):
    log.info('successful user logout', extra={'category': 'auth', 'status': 'success'})

@receiver(user_login_failed)
def user_login_failed_callback(sender, credentials, **kwargs):
    log.warning('failed user login', extra={'category': 'auth', 'status': 'failure'})
