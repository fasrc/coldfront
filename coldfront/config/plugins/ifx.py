'''
Config for ifxbilling
Installs ifxuser, ifxbilling, and author.  Sets AUTH_USER_MODEL
'''
import os
from decimal import Decimal
from coldfront.config.base import INSTALLED_APPS, MIDDLEWARE

INSTALLED_APPS = ['ifxuser'] + INSTALLED_APPS + ['author', 'ifxbilling', 'rest_framework.authtoken',]

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

# Ignore billing models in the django-author pre-save so that values are set directly
AUTHOR_IGNORE_MODELS = [
    'ifxbilling.BillingRecord',
    'ifxbilling.Transaction',
]
STANDARD_QUANTIZE = Decimal('0.0000')
TWO_DIGIT_QUANTIZE = Decimal('0.00')
