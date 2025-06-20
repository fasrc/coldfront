'''
Config for ifxbilling
Installs ifxuser, ifxbilling, and author.  Sets AUTH_USER_MODEL
'''
import os
from decimal import Decimal
from coldfront.config.base import MIDDLEWARE, INSTALLED_APPS

INSTALLED_APPS.insert(0, 'ifxuser')
INSTALLED_APPS += ['author', 'ifxbilling', 'rest_framework.authtoken', 'ifxreport', 'django_extensions']

MIDDLEWARE += [
    'author.middlewares.AuthorDefaultBackendMiddleware',
]

IFX_APP = {
    'name': 'coldfront',
    'token': os.environ.get('COLDFRONT_IFX_APP_TOKEN', 'aslkdfj'),
}

class GROUPS():
    ADMIN_GROUP_NAME = 'rc_admin'
    PREFERRED_BILLING_RECORD_APPROVAL_ACCOUNT_GROUP_NAME = 'Preferred Billing Record Approval Account'

class RATES():
    INTERNAL_RATE_NAME = 'Harvard Internal Rate'

class EMAILS():
    DEFAULT_EMAIL_FROM_ADDRESS = 'rchelp@rc.fas.harvard.edu'
    BILLING_CALCULATION_TASK_CC = 'akitzmiller@fas.harvard.edu'

# Ignore billing models in the django-author pre-save so that values are set directly
AUTHOR_IGNORE_MODELS = [
    'ifxbilling.BillingRecord',
    'ifxbilling.Transaction',
]
STANDARD_QUANTIZE = Decimal('0.0000')
TWO_DIGIT_QUANTIZE = Decimal('0.00')

MEDIA_ROOT = '/usr/src/app/media/'
MEDIA_URL = '/media/'

IFXREPORT_FILE_ROOT = os.path.join(MEDIA_ROOT, 'reports')
IFXREPORT_URL_ROOT = f'{MEDIA_URL}reports'

# Class to be used for rebalancing
REBALANCER_CLASS = 'coldfront.plugins.ifx.calculator.ColdfrontRebalance'

FIINELESS = os.environ.get('FIINELESS', 'FALSE').upper() == 'TRUE'
