'''
Models for ifxbilling plugin
'''
# pylint: disable=broad-exception-raised,broad-exception-caught,logging-fstring-interpolation
import logging
import json
from decimal import Decimal
from datetime import datetime
from django.utils import timezone
from django.db import models, connection, transaction
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from rest_framework.exceptions import ValidationError
from fiine.client import API as FiineAPI
from fiine.client import ApiException
from coldfront.core.allocation.models import AllocationUser, Allocation
from coldfront.core.resource.models import Resource
from coldfront.core.project.models import Project
from ifxbilling.models import ProductUsage, Product, Facility
from ifxbilling.fiine import create_new_product
from ifxuser.models import Organization

logger = logging.getLogger('ifx')


class ProjectOrganization(models.Model):
    '''
    Map ifxuser Organizations to Projects
    '''
    class Meta:
        unique_together = ('organization', 'project')

    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT
    )

    def __str__(self):
        return f'{self.project} - {self.organization}'

class AllocationUserProductUsage(models.Model):
    '''
    Link between ProductUsage and Allocation
    '''
    allocation_user = models.ForeignKey(
        AllocationUser.history.model,
        on_delete=models.PROTECT
    )
    product_usage = models.ForeignKey(
        ProductUsage,
        on_delete=models.CASCADE
    )

class ProductResource(models.Model):
    '''
    Link between Resources and Products
    '''
    resource = models.ForeignKey(
        Resource,
        on_delete=models.PROTECT
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )

class ProductAllocation(models.Model):
    '''
    Link between Allocations and Products
    '''
    allocation = models.ForeignKey(
        Allocation,
        on_delete=models.CASCADE
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )
    def __str__(self):
        return f'{self.allocation} - {self.product}'

def allocation_user_to_allocation_product_usage(allocation_user, product, overwrite=False, year=None, month=None):
    '''
    Converts an allocation_user to an allocation_product_usage.
    Unless overwrite flag is true, throws an exception if there is already an
    allocation_product_usage for this allocation user, year, and month.  Otherwise, removes existing AllocationUserProductUsage
    and ProductUsage records before creating new ones.

    Year and month can be overridden for "backdating"
    '''
    product_user = allocation_user.user
    if month is None:
        month = int(allocation_user.modified.strftime('%m'))
    if year is None:
        year = allocation_user.modified.year

    try:
        project_organization = allocation_user.allocation.project.projectorganization_set.first()
        if not project_organization:
            raise Exception(f'ProjectOrganization entry is missing for {allocation_user.allocation.project}')
        organization = project_organization.organization
    except ProjectOrganization.DoesNotExist as dne:
        raise Exception(f'Cannot map allocation_user {allocation_user} to organization') from dne

    aupus = AllocationUserProductUsage.objects.filter(
        product_usage__product=product,
        product_usage__product_user=product_user,
        product_usage__month=month,
        product_usage__year=year,
        product_usage__organization=organization,
        allocation_user__allocation=allocation_user.allocation, # Going by allocation because 1. user may be part of multiple and 2. this is a history value
    )
    if len(aupus) > 0:
        if overwrite:
            for aupu in aupus:
                aupu.product_usage.delete()
                aupu.delete()
        else:
            raise Exception(f'AllocationUserProductUsage already exists for use of {product} by {product_user} in month {month} of {year}')

    product_usage_data = {
        'product': product,
        'product_user': product_user,
        'month': month,
        'year': year,
        'start_date': timezone.make_aware(datetime(year, month, 1)),
        'organization': organization,
        'logged_by': product_user,
    }
    product_usage_data['quantity'] = allocation_user.usage_bytes
    # usage_bytes may be null
    if not product_usage_data['quantity']:
        product_usage_data['quantity'] = 0
    product_usage_data['units'] = 'b'
    tb_quantity = Decimal(product_usage_data['quantity'] / 1024**4).quantize(Decimal("100.0000"))
    product_usage_data['decimal_quantity'] = tb_quantity
    allocation_size = allocation_user.allocation.get_attribute('Storage Quota (TiB)')
    if not allocation_size:
        allocation_size = allocation_user.allocation.get_attribute('Storage Quota (TB)')
    product_usage_data['description'] = f"{tb_quantity.quantize(Decimal('0.00'))} TB of {allocation_size} TB allocation of {product_usage_data['product']} for {product_usage_data['product_user']} on {product_usage_data['start_date']}"
    # pylint: disable=unused-variable
    product_usage, created = ProductUsage.objects.get_or_create(**product_usage_data)
    aupu = AllocationUserProductUsage.objects.create(allocation_user=allocation_user.history.first(), product_usage=product_usage)
    return aupu

def update_allocation_product(allocation):
    '''
    For the given Allocation, create a Product and ProductAllocation if they don't exist
    or update the existing Product.

    The Resource is set as a parent of the Product.
    Returns the Product.
    '''
    resource = allocation.resources.first()
    if resource.resource_type.name == "Storage":

        if allocation.status.name != 'Active':
            logger.debug(f'Allocation {allocation} is not active')
            return

        if not allocation.get_attribute(name='RequiresPayment') == 'True':
            logger.debug(f'Allocation {allocation} does not require payment')
            return

        with transaction.atomic():
            tb_str = None
            attr_val = allocation.get_attribute(name='Storage Quota (TB)')
            if attr_val:
                tb_str = f"{attr_val} TB"
            else:
                attr_val = allocation.get_attribute(name='Storage Quota (TiB)')
                if attr_val:
                    tb_str = f"{attr_val} TiB"
            if tb_str:
                dir_str = allocation.get_attribute(name='Subdirectory')
                if dir_str:
                    dir_str = f' at {dir_str}'
                else:
                    dir_str = f' for {allocation.project.title}'
                product_name = f'{tb_str} of {resource.name}{dir_str}'
                if len(product_name) > 100:
                    raise Exception(f'Product name {product_name} is too long')
                product_description = product_name
                facility = Facility.objects.get(name='Research Computing Storage')
                billing_calculator = 'coldfront.plugins.ifx.calculator.NewColdfrontBillingCalculator'
                product_category = 'Storage Allocation'
                object_code_category = 'Technical Services'
                if not resource.productresource_set.first():
                    raise Exception(f'Resource {resource} has no ProductResource')
                resource_product = resource.productresource_set.first().product
                allocation_organization = None
                try:
                    allocation_organization = allocation.project.projectorganization_set.first().organization
                except Exception as e:
                    logger.error(f'Allocation {allocation} has no project organization set')
                    raise e
                try:
                    pa = ProductAllocation.objects.get(allocation=allocation)
                    product = pa.product
                    if not hasattr(settings, 'FIINELESS') or not settings.FIINELESS:
                        fiine_product = FiineAPI.readProduct(product_number=product.product_number)
                        fiine_product.product_name = product_name
                        fiine_product.product_description = product_description
                        fiine_product.facility = facility.name
                        fiine_product.parent = {
                            'product_number': resource_product.product_number,
                        }
                        fiine_product.product_organization = {
                            'ifxorg': allocation_organization.ifxorg,
                        }
                        fiine_product.billing_calculator = billing_calculator
                        fiine_product.product_category = product_category
                        fiine_product.object_code_category = object_code_category
                        fiine_product_dict = fiine_product.to_dict()
                        fiine_product_dict.pop('product_number')
                        updated_fiine_product = FiineAPI.updateProduct(product_number=product.product_number, **fiine_product_dict)
                        for field in ['product_name', 'product_description', 'object_code_category']:
                            setattr(product, field, getattr(updated_fiine_product, field))
                    else:
                        product.product_name = product_name
                        product.product_description = product_description
                        product.object_code_category = object_code_category
                        product.billing_calculator = billing_calculator
                        product.product_category = product_category
                    product.facility = facility
                    product.product_organization = allocation_organization
                    product.parent = resource_product
                    product.save()
                    return product
                except ProductAllocation.DoesNotExist:
                    pa = ProductAllocation(allocation=allocation)
                    # Create a new Product.  create_new_product method knows about FIINELESS
                    product = create_new_product(
                        product_name=product_name,
                        product_description=product_description,
                        facility=facility,
                        parent=resource_product,
                        product_organization=allocation_organization,
                        object_code_category='Technical Services',
                        billing_calculator='coldfront.plugins.ifx.calculator.NewColdfrontBillingCalculator',
                        product_category='Storage Allocation',
                    )
                    pa.product = product
                    pa.save()
                except ValidationError as e:
                    logger.error(f'Validation error creating product for allocation {allocation}: {e}')
                except Exception as e:
                    logger.error(f'Error creating product for allocation {allocation}: {e}')
                    raise
            else:
                logger.error(f'Allocation {allocation} has no Storage Quota (TB) or Storage Quota (TiB) attribute')
                raise Exception(f'Allocation {allocation} has no Storage Quota (TB) or Storage Quota (TiB) attribute')

def allocation_post_save(sender, instance, **kwargs):
    '''
    Create a Product, ProductAllocation for each Allocation
    '''
    if not kwargs.get('raw'):
        try:
            update_allocation_product(instance)
        except Exception as e:
            logger.error(f'Error creating product for allocation {instance}: {e}')


@receiver(post_save, sender=Resource)
def resource_post_save(sender, instance, **kwargs):
    '''
    Ensure that there is a Product for each Resource
    '''
    if not kwargs.get('raw') and not instance.resource_type.name in ["Storage Tier", "Cluster", "Cluster Partition", "Compute Node"] and instance.requires_payment:
        try:
            product_resource = ProductResource.objects.get(resource=instance)
        except ProductResource.DoesNotExist:
            # Need to create a Product and ProductResource for this Resource
            products = []
            try:
                if not settings.FIINELESS:
                    products = FiineAPI.listProducts(product_name=instance.name)
                facility = Facility.objects.get(name='Research Computing Storage')
                if not products:
                    product = create_new_product(product_name=instance.name, product_description=instance.name, facility=facility)
                else:
                    fiine_product = products[0].to_dict()
                    fiine_product.pop('object_code_category')
                    fiine_product['facility'] = facility
                    fiine_product['billing_calculator'] = 'coldfront.plugins.ifx.calculator.NewColdfrontBillingCalculator'
                    (product, created) = Product.objects.get_or_create(**fiine_product)
                product_resource = ProductResource.objects.create(product=product, resource=instance)
            except ApiException as e:
                if e.status == 400:
                    msg = json.loads(e.body)
                if 'Duplicate' in str(e):
                    msg = 'Duplicate entry in Fiine'
                if e.status == 401:
                    msg = 'Unauthorized'
                logger.error(f'Error creating Product for Resource {instance}: {msg}')
                raise Exception(msg) from e
            except Exception as e:
                logger.error(f'Error creating Product for Resource {instance}: {e}')
                raise

class SuUser(get_user_model()):
    '''
    This is just so that we can have an admin interface with su
    '''
    class Meta:
        proxy = True


def get_resource_allocation_authorization_map():
    '''
    What labs have what auth for products, in tall skinny form, ready for Excel Pivot Table
    All projects / organizations are returned along with any allocations and expense code authorizations
    '''

    # Three sections of query
    # 1. Groups with user product account authorizations
    # 2. Groups with user account authorizations (which cover all products / resources)
    # 3. Groups with neither user product account or user account authorizations
    #
    # project_organizations are left joined so that we can find the unmapped projects
    # parent orgs are left joined, since many of those are not mapped
    sql = '''
        select
            p.title as project,
            o.name as organization,
            r.name as resource,
            al.id as allocation_id,
            a.name as account,
            parent.name as parent
        from
            project_project p
            inner join allocation_allocation al on al.project_id = p.id
            inner join allocation_allocation_resources ar on ar.allocation_id=al.id
            inner join resource_resource r on r.id=ar.resource_id
            inner join ifx_productresource ipr on ipr.resource_id = r.id
            inner join product pr on pr.id = ipr.product_id
            left join ifx_projectorganization po on p.id=po.project_id
            left join nanites_organization o on po.organization_id=o.id
            left join account a on o.id=a.organization_id
            left join user_product_account upa on upa.account_id = a.id
            left join nanites_org_relation rel on rel.child_id = o.id
            left join nanites_organization parent on parent.id = rel.parent_id
        where
            exists (select 1 from user_product_account upa where upa.account_id = a.id and upa.product_id=pr.id) and
            p.status_id in (1,2)
        union
        select
            p.title as project,
            o.name as organization,
            r.name as resource,
            al.id as allocation_id,
            a.name as account,
            parent.name as parent
        from
            project_project p
            inner join allocation_allocation al on al.project_id = p.id
            inner join allocation_allocation_resources ar on ar.allocation_id=al.id
            inner join resource_resource r on r.id=ar.resource_id
            inner join ifx_productresource ipr on ipr.resource_id = r.id
            inner join product pr on pr.id = ipr.product_id
            inner join ifx_projectorganization po on p.id=po.project_id
            inner join nanites_organization o on po.organization_id=o.id
            inner join account a on o.id=a.organization_id
            inner join user_account ua on ua.account_id = a.id
            left join nanites_org_relation rel on rel.child_id = o.id
            left join nanites_organization parent on parent.id = rel.parent_id
        where
            p.status_id in (1,2)
        union
        select
            p.title as project,
            o.name as organization,
            r.name as resource,
            al.id as allocation_id,
            '' as account,
            parent.name as parent
        from
            project_project p
            inner join allocation_allocation al on al.project_id = p.id
            inner join allocation_allocation_resources ar on ar.allocation_id=al.id
            inner join resource_resource r on r.id=ar.resource_id
            inner join ifx_productresource ipr on ipr.resource_id = r.id
            inner join product pr on pr.id = ipr.product_id
            left join ifx_projectorganization po on p.id=po.project_id
            left join nanites_organization o on po.organization_id=o.id
            left join nanites_org_relation rel on rel.child_id = o.id
            left join nanites_organization parent on parent.id = rel.parent_id
        where
            p.status_id in (1,2) and
            not exists (
                select 1
                from
                    user_product_account upa inner join account a on upa.account_id = a.id
                where
                    upa.product_id=pr.id and
                    a.organization_id=o.id
            ) and
            not exists (
                select 1
                from
                    user_account ua inner join account a on ua.account_id = a.id
                where
                    a.organization_id=o.id
            )
    '''
    cursor = connection.cursor()
    cursor.execute(sql)
    result = [
        ['Project', 'Organization', 'Resource', 'Allocation ID', 'Account', 'Parent']
    ]
    for row in cursor.fetchall():
        result.append(row)

    return result
