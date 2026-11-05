"""Project offboarding: PI selects a project, fills out the offboarding form,
and the answers are emailed to EMAIL_TICKET_SYSTEM_ADDRESS."""
import logging

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic.edit import FormView

from coldfront.core.project.models import Project, ProjectUser
from coldfront.core.utils.common import import_from_settings
from coldfront.core.utils.mail import send_email

logger = logging.getLogger(__name__)


YES_NO = [('yes', 'Yes'), ('no', 'No')]


def pi_projects(user):
    """Projects the given user is PI of that can still be offboarded."""
    return Project.objects.filter(pi=user, status__name__in=['New', 'Active']).order_by('title')


def storage_allocations(project):
    return project.allocation_set.filter(
        status__name='Active', resources__resource_type__name='Storage'
    ).distinct().order_by('resources__name')


def allocation_path(allocation):
    try:
        return allocation.path or str(allocation.get_parent_resource)
    except Exception:  # missing 'Subdirectory' attribute type, etc.
        return str(allocation.get_parent_resource)


def group_members(project):
    return ProjectUser.objects.filter(
        project=project, status__name='Active'
    ).exclude(user=project.pi).select_related('user').order_by('user__username')


class OffboardingProjectSelectForm(forms.Form):
    project = forms.ModelChoiceField(queryset=Project.objects.none(), empty_label=None)

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['project'].queryset = pi_projects(user)


class OffboardingForm(forms.Form):
    alternative_email = forms.EmailField(required=False, label='Alternative email')
    offboarding_date = forms.DateField(
        label='Date project will be completed or when leaving the university',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )

    def __init__(self, project, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self.allocations = list(storage_allocations(project))
        self.members = list(group_members(project))
        for alloc in self.allocations:
            self._add_allocation_fields(alloc)
        for pu in self.members:
            self.fields[f'offboard_{pu.pk}'] = forms.BooleanField(required=False)
            self.fields[f'sponsor_{pu.pk}'] = forms.CharField(required=False, max_length=255)

    def _add_allocation_fields(self, alloc):
        p = f'alloc_{alloc.pk}_'
        radio = forms.RadioSelect
        self.fields[p + 'retain'] = forms.ChoiceField(choices=YES_NO, widget=radio)
        self.fields[p + 'retain_duration'] = forms.CharField(required=False)
        self.fields[p + 'retain_funding'] = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 3}))
        self.fields[p + 'delete'] = forms.ChoiceField(choices=YES_NO, widget=radio)
        self.fields[p + 'move'] = forms.ChoiceField(choices=YES_NO, widget=radio)
        self.fields[p + 'move_within_harvard'] = forms.ChoiceField(choices=YES_NO, widget=radio, required=False)
        self.fields[p + 'move_recipient'] = forms.CharField(required=False)
        self.fields[p + 'move_destination'] = forms.CharField(required=False)

    def allocation_rows(self):
        """Bound fields grouped per allocation, for template rendering."""
        rows = []
        for alloc in self.allocations:
            p = f'alloc_{alloc.pk}_'
            rows.append({
                'allocation': alloc,
                'path': allocation_path(alloc),
                'prefix': p,
                **{name: self[p + name] for name in (
                    'retain', 'retain_duration', 'retain_funding', 'delete', 'move',
                    'move_within_harvard', 'move_recipient', 'move_destination')},
            })
        return rows

    def member_rows(self):
        return [
            {'project_user': pu, 'offboard': self[f'offboard_{pu.pk}'], 'sponsor': self[f'sponsor_{pu.pk}']}
            for pu in self.members
        ]

    def clean(self):
        cleaned = super().clean()
        required_msg = 'This field is required.'
        for alloc in self.allocations:
            p = f'alloc_{alloc.pk}_'
            if cleaned.get(p + 'retain') == 'yes':
                for name in ('retain_duration', 'retain_funding'):
                    if not cleaned.get(p + name, '').strip():
                        self.add_error(p + name, required_msg)
            if cleaned.get(p + 'move') == 'yes':
                within = cleaned.get(p + 'move_within_harvard')
                if not within:
                    self.add_error(p + 'move_within_harvard', required_msg)
                elif within == 'yes' and not cleaned.get(p + 'move_recipient', '').strip():
                    self.add_error(p + 'move_recipient', required_msg)
                elif within == 'no' and not cleaned.get(p + 'move_destination', '').strip():
                    self.add_error(p + 'move_destination', required_msg)
        return cleaned

    def email_body(self, user):
        c = self.cleaned_data
        project = self.project
        yn = lambda v: 'Yes' if v == 'yes' else 'No'
        lines = [
            f'Offboarding form submitted by {user.get_full_name() or user.username} ({user.username})',
            '',
            f'Project: {project.title}',
            f'Email: {user.email}',
            f'Alternative email: {c.get("alternative_email") or "(none)"}',
            f'Expected date of offboarding: {c["offboarding_date"].isoformat()}',
            '',
            'STORAGE',
        ]
        if not self.allocations:
            lines.append('  (no active storage allocations)')
        for alloc in self.allocations:
            p = f'alloc_{alloc.pk}_'
            lines += [
                f'  Allocation: {allocation_path(alloc)} (id {alloc.pk})',
                f'    Retain in current location: {yn(c[p + "retain"])}',
            ]
            if c[p + 'retain'] == 'yes':
                lines += [
                    f'      Retention period: {c[p + "retain_duration"]}',
                    f'      Funding / billing code and contact: {c[p + "retain_funding"]}',
                ]
            lines.append(f'    Delete: {yn(c[p + "delete"])}')
            lines.append(f'    Move: {yn(c[p + "move"])}')
            if c[p + 'move'] == 'yes':
                if c[p + 'move_within_harvard'] == 'yes':
                    lines.append(f'      Moving within Harvard to: {c[p + "move_recipient"]}')
                else:
                    lines.append(f'      Moving outside Harvard to: {c[p + "move_destination"]}')
        lines += ['', 'ACCOUNTS']
        if not self.members:
            lines.append('  (no other group members)')
        for pu in self.members:
            if c[f'offboard_{pu.pk}']:
                status = 'fully offboard'
            else:
                sponsor = c[f'sponsor_{pu.pk}'].strip()
                status = f'staying; new sponsor: {sponsor}' if sponsor else 'staying; no new sponsor given'
            lines.append(f'  {pu.user.username} ({pu.user.get_full_name()}, {pu.user.email}): {status}')
        return '\n'.join(lines)


class PIRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = '/'

    def test_func(self):
        user = self.request.user
        if not user.userprofile.is_pi:
            messages.error(self.request, 'Only PIs can offboard a project.')
            return False
        return True


class OffboardingProjectSelectView(PIRequiredMixin, FormView):
    form_class = OffboardingProjectSelectForm
    template_name = 'project/offboarding_select.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        return redirect('project-offboarding', pk=form.cleaned_data['project'].pk)


class OffboardingFormView(PIRequiredMixin, FormView):
    form_class = OffboardingForm
    template_name = 'project/offboarding_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(Project, pk=kwargs['pk'])
        return super().dispatch(request, *args, **kwargs)

    def test_func(self):
        if not super().test_func():
            return False
        if self.project.pi_id != self.request.user.pk:
            messages.error(self.request, 'You can only offboard projects you are the PI of.')
            return False
        return True

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['project'] = self.project
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['project'] = self.project
        context['allocation_rows'] = context['form'].allocation_rows()
        context['member_rows'] = context['form'].member_rows()
        context['select_url'] = reverse('project-offboarding-select')
        return context

    def form_valid(self, form):
        ticket_address = import_from_settings('EMAIL_TICKET_SYSTEM_ADDRESS', '')
        if not ticket_address:
            logger.error('EMAIL_TICKET_SYSTEM_ADDRESS is not configured; offboarding form not sent.')
            messages.error(self.request, 'Offboarding form could not be sent: no ticket system address is configured.')
            return self.form_invalid(form)
        user = self.request.user
        send_email(
            f'Offboarding form: {self.project.title}',
            form.email_body(user),
            import_from_settings('EMAIL_SENDER', ''),
            [ticket_address],
        )
        messages.success(self.request, 'offboarding form sent.')
        return redirect('home')
