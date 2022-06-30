from django.db.models import Count, Sum, Q, Value
from django.shortcuts import get_object_or_404, render
from django.views.generic import DetailView, ListView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from coldfront.core.project.models import Project
from coldfront.core.utils.common import import_from_settings
from coldfront.core.field_of_science.models import FieldOfScience
from coldfront.core.allocation.models import Allocation, AllocationUser 
from coldfront.core.allocation.forms import AllocationInvoiceUpdateForm


ALLOCATION_ENABLE_ALLOCATION_RENEWAL = import_from_settings(
    'ALLOCATION_ENABLE_ALLOCATION_RENEWAL', True)


def set_proj_update_permissions(allocation_obj, user):
    if user.is_superuser:
        return True
    if allocation_obj.project.projectuser_set.filter(user=user).exists():
        project_user = allocation_obj.project.projectuser_set.get(user=user)
        if project_user.role.name == 'Manager':
            return True
    return False


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
        department_obj = get_object_or_404(FieldOfScience, pk=pk)
        project_objs = department_obj.project_set.all()\
                    .annotate(total_quota=Sum('allocation__allocationattribute__value', filter=(Q(allocation__allocationattribute__allocation_attribute_type_id=1))\
                                &(Q(allocation__status_id=1))))#\

        price_dict = {1:4.16, 17:20.80, 8:20.80, 7:.41, 2:4.16 }

        for p in project_objs:
            alloc = p.allocation_set.all().\
                    filter(allocationattribute__allocation_attribute_type_id=1).\
                    values('resources','allocationattribute__value')
            p.price_detail = " || ".join(f"{a['allocationattribute__value']}*${price_dict[a['resources']]} = "\
                        f"{float(a['allocationattribute__value'])*price_dict[a['resources']]}" for a in alloc)
            p.total_price = sum(float(a['allocationattribute__value']) * price_dict[a['resources']] for a in alloc)
            
        context['full_price'] = sum(p.total_price for p in project_objs)
        context['projects'] = project_objs
        
        allocation_objs = Allocation.objects.filter(project_id__in=[o.id for o in project_objs])
        context['allocations'] = allocation_objs

        allocation_users = AllocationUser.objects.filter(allocation_id__in=[o.id for o in allocation_objs]).filter(status_id=1)\
                .exclude(
            status__name__in=['Removed']).exclude(usage_bytes__isnull=True).order_by('user__username')

        
        initial_data = {
            'status': allocation_objs.first().status,
        }
        form = AllocationInvoiceUpdateForm(initial=initial_data)
        context['form'] = form

        context['allocation'] = allocation_objs.first()
        context['department'] = department_obj

        # Can the user update the project?
        context['is_allowed_to_update_project'] = set_proj_update_permissions(
                                                    allocation_objs.first(), self.request.user)
        context['allocation_users'] = allocation_users

        if self.request.user.is_superuser:
            notes = allocation_objs.first().allocationusernote_set.all()
        else:
            notes = allocation_objs.first().allocationusernote_set.filter(
                is_private=False)

        context['notes'] = notes
        context['ALLOCATION_ENABLE_ALLOCATION_RENEWAL'] = ALLOCATION_ENABLE_ALLOCATION_RENEWAL
        return context


    def get(self, request, *args, **kwargs):
        pk = self.kwargs.get('pk')
        context = self.get_context_data()
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

