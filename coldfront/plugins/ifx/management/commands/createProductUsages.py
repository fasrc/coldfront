# -*- coding: utf-8 -*-

'''
Create ProductUsages and AllocationUserProductUsages from AllocationUsers for a specified month
'''
# pylint: disable=broad-exception-raised,broad-exception-caught,logging-fstring-interpolation

import logging
from django.utils import timezone
from django.core.management.base import BaseCommand
from coldfront.core.resource.models import Resource
from coldfront.core.allocation.models import AllocationUser, Allocation, AllocationUserStatusChoice
from coldfront.plugins.ifx.models import allocation_user_to_allocation_product_usage
from ifxbilling.models import Product

logger = logging.getLogger('')

class Command(BaseCommand):
    '''
    Create ProductUsages and AllocationUserProductUsages from AllocationUsers for a specified month
    '''
    help = 'Create ProductUsages for the given year and month.  Use --overwrite to remove existing records and recreate. Usage:\n' + \
        './manage.py createProductUsages --year 2021 --month 3\n\n' + \
        'Use --select-year and --select-month to use allocation information from a different month / year.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            dest='year',
            default=timezone.now().year,
            help='Year for calculation',
        )
        parser.add_argument(
            '--month',
            dest='month',
            default=timezone.now().month,
            help='Month for calculation',
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Remove existing product usages',
        )
        parser.add_argument(
            '--select-year',
            dest='select_year',
            help='Select allocation data from this year if different from --year',
        )
        parser.add_argument(
            '--select-month',
            dest='select_month',
            help='Select allocation data from this month if different from --month',
        )
        parser.add_argument(
            '--product-names',
            dest='productstr',
            help='Create for specified products (comma separated list)'
        )

    def handle(self, *args, **kwargs):
        month = select_month = int(kwargs['month'])
        year = select_year = int(kwargs['year'])
        products = []
        if 'select_month' in kwargs and kwargs['select_month']:
            select_month = int(kwargs['select_month'])
        if 'select_year' in kwargs and kwargs['select_year']:
            select_year = int(kwargs['select_year'])
        if 'productstr' in kwargs and kwargs['productstr']:
            product_names = kwargs['productstr'].split(',')
            products = Product.objects.filter(product_name__in=product_names)
            print(f'Only processing {product_names}')

        overwrite = kwargs['overwrite']
        successes = 0
        errors = []
        resources = Resource.objects.filter(requires_payment=True)
        for resource in resources:
            product_resources = resource.productresource_set.all()
            if len(product_resources) == 1:
                product = product_resources[0].product

                if not products or product in products:
                    # Get the AllocationUser records
                    allocations = Allocation.objects.filter(resources__in=[resource], status__name='Active')
                    print(f'Processing {len(allocations)} allocations for {resource}')
                    for allocation in allocations:
                        requires_payment = allocation.get_attribute('RequiresPayment')
                        if requires_payment == 'True':
                            print(f'Generating product usages for {allocation}')
                            if not AllocationUser.objects.filter(allocation=allocation).count():
                                # If there are no allocation users, assign the PI
                                pi = allocation.project.pi
                                AllocationUser.objects.create(allocation=allocation, user=pi, status=AllocationUserStatusChoice.objects.get(name='Active'))
                                logger.info(f'Set PI {pi} as a user for {allocation}')

                            allocation_product = None
                            try:
                                allocation_product = allocation.productallocation_set.first().product
                            except Exception as e:
                                logger.error(f'Error getting product allocation for {allocation}: {e}')

                            for allocation_user in AllocationUser.objects.filter(allocation=allocation):
                                try:
                                    if allocation_product:
                                        allocation_user_to_allocation_product_usage(allocation_user, allocation_product, overwrite, month=month, year=year)
                                    else:
                                        allocation_user_to_allocation_product_usage(allocation_user, product, overwrite, month=month, year=year)
                                    successes += 1
                                except Exception as e:
                                    if 'AllocationUserProductUsage already exists for use of' not in str(e):
                                        logger.exception(e)
                                    errors.append(f'Error creating product usage for {product} and user {allocation_user.user}: {e}')
                        else:
                            print(f'Allocation {allocation} does not require payment')
            else:
                errors.append(f'Unable to fine a Product for resource {resource}')
        print(f'{successes} records successfully created.')
        if errors:
            print('Errors: %s' % "\n".join(errors))
        logger.debug('Done')

