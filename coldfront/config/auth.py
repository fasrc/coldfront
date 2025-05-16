from coldfront.config.env import ENV
from coldfront.config.base import INSTALLED_APPS, AUTHENTICATION_BACKENDS, TEMPLATES

#------------------------------------------------------------------------------
# ColdFront default authentication settings
#------------------------------------------------------------------------------
AUTHENTICATION_BACKENDS += [
    'django.contrib.auth.backends.ModelBackend',
]

LOGIN_URL = '/user/login'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = ENV.str('LOGOUT_REDIRECT_URL', LOGIN_URL)

SU_LOGIN_CALLBACK = "coldfront.core.utils.common.su_login_callback"
SU_LOGOUT_REDIRECT_URL = "/su/login/"

SESSION_COOKIE_AGE = ENV.int('SESSION_INACTIVITY_TIMEOUT', default=120 * 60)
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_SAMESITE  = 'Strict'
## Need to test with True
SESSION_COOKIE_SECURE = False

#------------------------------------------------------------------------------
# Enable administrators to login as other users
#------------------------------------------------------------------------------
if ENV.bool('ENABLE_SU', default=True):
    AUTHENTICATION_BACKENDS += ['django_su.backends.SuBackend', ]
    INSTALLED_APPS.insert(0, 'django_su')
    TEMPLATES[0]['OPTIONS']['context_processors'].extend(['django_su.context_processors.is_su', ])

AUTH_USER_MODEL = 'ifxuser.IfxUser'
