from django.db.models import Count
from django.shortcuts import get_object_or_404, render
from coldfront.core.field_of_science.models import FieldOfScience
from coldfront.core.allocation.models import Allocation 
from coldfront.core.allocation.forms import (AllocationAddUserForm,
                                             AllocationAttributeDeleteForm,
                                             AllocationChangeForm,
                                             AllocationChangeNoteForm,
                                             AllocationAttributeChangeForm,
                                             AllocationAttributeUpdateForm,
                                             AllocationForm,
                                             AllocationInvoiceNoteDeleteForm,
                                             AllocationInvoiceUpdateForm )
from coldfront.core.allocation.utils import (generate_guauge_data_from_usage,
                                             get_user_resources)
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import DetailView, ListView, TemplateView
from coldfront.core.utils.common import get_domain_url, import_from_settings


ALLOCATION_ENABLE_ALLOCATION_RENEWAL = import_from_settings(
    'ALLOCATION_ENABLE_ALLOCATION_RENEWAL', True)
ALLOCATION_DEFAULT_ALLOCATION_LENGTH = import_from_settings(
    'ALLOCATION_DEFAULT_ALLOCATION_LENGTH', 365)
ALLOCATION_ENABLE_CHANGE_REQUESTS_BY_DEFAULT = import_from_settings(
    'ALLOCATION_ENABLE_CHANGE_REQUESTS_BY_DEFAULT', True)

EMAIL_ENABLED = import_from_settings('EMAIL_ENABLED', False)
if EMAIL_ENABLED:
    EMAIL_SENDER = import_from_settings('EMAIL_SENDER')
    EMAIL_TICKET_SYSTEM_ADDRESS = import_from_settings(
        'EMAIL_TICKET_SYSTEM_ADDRESS')
    EMAIL_OPT_OUT_INSTRUCTION_URL = import_from_settings(
        'EMAIL_OPT_OUT_INSTRUCTION_URL')
    EMAIL_SIGNATURE = import_from_settings('EMAIL_SIGNATURE')
    EMAIL_CENTER_NAME = import_from_settings('CENTER_NAME')

PROJECT_ENABLE_PROJECT_REVIEW = import_from_settings(
    'PROJECT_ENABLE_PROJECT_REVIEW', False)
INVOICE_ENABLED = import_from_settings('INVOICE_ENABLED', False)
if INVOICE_ENABLED:
    INVOICE_DEFAULT_STATUS = import_from_settings(
        'INVOICE_DEFAULT_STATUS', 'Pending Payment')

ALLOCATION_ACCOUNT_ENABLED = import_from_settings(
    'ALLOCATION_ACCOUNT_ENABLED', False)
ALLOCATION_ACCOUNT_MAPPING = import_from_settings(
    'ALLOCATION_ACCOUNT_MAPPING', {})


def return_alloc_attr_set(allocation_obj, is_su):
    if is_su:
        return allocation_obj.allocationattribute_set.\
                        all().order_by('allocation_attribute_type__name')
    return allocation_obj.allocationattribute_set.\
                    filter(allocation_attribute_type__is_private=False)



def return_allocation_bytes_values(attributes_with_usage, allocation_users):
    # usage_bytes_list written the way it should work
    usage_bytes_list = [u.usage_bytes for u in allocation_users]
    user_usage_sum = sum(usage_bytes_list)
    allocation_quota_bytes = next((a for a in attributes_with_usage if \
            a.allocation_attribute_type.name == "Quota_in_bytes"), "None")
    if allocation_quota_bytes != "None":
        allocation_usage_bytes = float(allocation_quota_bytes.allocationattributeusage.value)
    else:
        bytes_in_tb = 1099511627776
        allocation_quota_tb = next((a for a in attributes_with_usage if \
            a.allocation_attribute_type.name == "Storage Quota (TB)"), "None")
        allocation_usage_tb = float(allocation_quota_tb.allocationattributeusage.value)
        allocation_quota_in_tb = float(allocation_quota_tb.value)
        allocation_quota_bytes = float(allocation_quota_in_tb)*bytes_in_tb
        allocation_usage_bytes = allocation_usage_tb*bytes_in_tb if \
                    allocation_usage_tb != 0 else user_usage_sum
    return (allocation_quota_bytes, allocation_usage_bytes)



def set_proj_update_permissions(allocation_obj, user):
    if user.is_superuser:
        return True
    if allocation_obj.project.projectuser_set.filter(user=user).exists():
        project_user = allocation_obj.project.projectuser_set.get(user=user)
        if project_user.role.name == 'Manager':
            return True
    return False

def generate_email_receiver_list(allocation_users):
    email_receiver_list = []
    for allocation_user in allocation_users:
        if allocation_user.allocation.project.projectuser_set.get(user=allocation_user.user).enable_notifications:
            email_receiver_list.append(allocation_user.user.email)
    return email_receiver_list

def generate_allocation_customer_template(resource_name, allocation_url):
    template_context = {
        'center_name': EMAIL_CENTER_NAME,
        'resource': resource_name,
        'allocation_url': allocation_url,
        'signature': EMAIL_SIGNATURE,
        'opt_out_instruction_url': EMAIL_OPT_OUT_INSTRUCTION_URL
    }
    return template_context


class DepartmentAllocationListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = FieldOfScience
    template_name = 'field_of_science/department_allocation_invoice_list.html'
    context_object_name = 'department_list'

    def test_func(self):
        """ UserPassesTestMixin Tests"""
        if self.request.user.is_superuser:
            return True

        if self.request.user.has_perm('allocation.can_manage_invoice'):
            return True

        messages.error(
            self.request, 'You do not have permission to manage invoices.')
        return False

    def get_queryset(self):
        """Connect FieldofScience entries to Allocations via Projects
        """
        
        dept_allocations = FieldOfScience.objects.values(
            'id',
            'description',
            'fos_nsf_abbrev',
            'project',
            'project__allocation'
            ).annotate(project_count=Count('project'))\
            .filter(project_count__gt=0)
            #, allocation_count=Count('project__allocation'))\
        return dept_allocations

class DepartmentAllocationInvoiceDetailView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    model = FieldOfScience
    template_name = 'field_of_science/department_allocation_invoice_detail.html'
    context_object_name = 'department_invoice'

    def test_func(self):
        """ UserPassesTestMixin Tests"""
        if self.request.user.is_superuser:
            return True

        if self.request.user.has_perm('allocation.can_manage_invoice'):
            return True

    def get_context_data(self, **kwargs):
        """Create all the variables for allocation_invoice_detail.html

        """
        context = super().get_context_data(**kwargs)
        pk = self.kwargs.get('pk')
        allocation_obj = get_object_or_404(Allocation, pk=pk)
        allocation_users = allocation_obj.allocationuser_set.exclude(
            status__name__in=['Removed']).exclude(usage_bytes__isnull=True).order_by('user__username')

        alloc_attr_set = return_alloc_attr_set(allocation_obj,
                                                self.request.user.is_superuser)

        attributes_with_usage = [a for a in alloc_attr_set if hasattr(a, 'allocationattributeusage')]
        attributes = [a for a in alloc_attr_set]

        guage_data = []
        invalid_attributes = []
        for attribute in attributes_with_usage:
            try:
                guage_data.append(generate_guauge_data_from_usage(attribute.allocation_attribute_type.name,
                            float(attribute.value), float(attribute.allocationattributeusage.value)))
            except ValueError:
                logger.error("Allocation attribute '%s' is not an int but has a usage",
                            attribute.allocation_attribute_type.name)
                invalid_attributes.append(attribute)

        for a in invalid_attributes:
            attributes_with_usage.remove(a)


        allocation_quota_bytes, allocation_usage_bytes = return_allocation_bytes_values(attributes_with_usage, allocation_users)
        context['allocation_quota_bytes'] = allocation_quota_bytes
        context['allocation_usage_bytes'] = allocation_usage_bytes

        context['guage_data'] = guage_data
        context['attributes_with_usage'] = attributes_with_usage
        context['attributes'] = attributes

        # set price
        tier = allocation_obj.get_resources_as_string.split("/")[1]
        price_dict = {"tier0":4.16, "tier1":20.80, "tier2": 100/12, "tier3":.41}
        context['price'] = price_dict[tier]

        # Can the user update the project?
        context['is_allowed_to_update_project'] = set_proj_update_permissions(
                                                    allocation_obj, self.request.user)
        context['allocation_users'] = allocation_users

        if self.request.user.is_superuser:
            notes = allocation_obj.allocationusernote_set.all()
        else:
            notes = allocation_obj.allocationusernote_set.filter(
                is_private=False)

        context['notes'] = notes
        context['ALLOCATION_ENABLE_ALLOCATION_RENEWAL'] = ALLOCATION_ENABLE_ALLOCATION_RENEWAL
        return context


    def get(self, request, *args, **kwargs):
        pk = self.kwargs.get('pk')
        allocation_obj = get_object_or_404(Allocation, pk=pk)

        initial_data = {
            'status': allocation_obj.status,
        }

        form = AllocationInvoiceUpdateForm(initial=initial_data)

        context = self.get_context_data()
        context['form'] = form
        context['allocation'] = allocation_obj

        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        pk = self.kwargs.get('pk')
        allocation_obj = get_object_or_404(Allocation, pk=pk)

        initial_data = {
            'status': allocation_obj.status,
        }
        form = AllocationInvoiceUpdateForm(
            request.POST, initial=initial_data)

        if form.is_valid():
            form_data = form.cleaned_data
            allocation_obj.status = form_data.get('status')
            allocation_obj.save()
            messages.success(request, 'Allocation updated!')
        else:
            for error in form.errors:
                messages.error(request, error)
        return HttpResponseRedirect(reverse('allocation-invoice-detail', kwargs={'pk': pk}))

