import datetime
import re

from django import forms
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.safestring import mark_safe

from coldfront.core.project.models import (
    Project,
    ProjectAttribute,
    ProjectReview,
    ProjectUser,
    ProjectUserRoleChoice,
)
from coldfront.core.allocation.forms import ExpenseCodeField
from coldfront.core.utils.common import import_from_settings

EMAIL_DIRECTOR_PENDING_PROJECT_REVIEW_EMAIL = import_from_settings(
    'EMAIL_DIRECTOR_PENDING_PROJECT_REVIEW_EMAIL')
EMAIL_ADMIN_LIST = import_from_settings('EMAIL_ADMIN_LIST', [])
EMAIL_DIRECTOR_EMAIL_ADDRESS = import_from_settings(
    'EMAIL_DIRECTOR_EMAIL_ADDRESS', '')
PENDING_ACTIVE_ALLOCATION_STATUSES = import_from_settings(
    'PENDING_ACTIVE_ALLOCATION_STATUSES', ['Active', 'New', 'Renewal Requested', 'Payment Pending', 'Payment Requested', 'Paid'])

class ProjectSearchForm(forms.Form):
    """ Search form for the Project list page.
    """
    PROJECT_TITLE = 'Project Title'
    LAST_NAME = 'Last Name'
    USERNAME = 'Username'
    FIELD_OF_SCIENCE = 'Field of Science'

    title = forms.CharField(
        label = PROJECT_TITLE, max_length=100, required=False
        )
    last_name = forms.CharField(
        label=LAST_NAME, max_length=100, required=False)
    username = forms.CharField(label=USERNAME, max_length=100, required=False)
    field_of_science = forms.CharField(
        label=FIELD_OF_SCIENCE, max_length=100, required=False)
    show_all_projects = forms.BooleanField(initial=False, required=False)


class ProjectAddUserForm(forms.Form):
    username = forms.CharField(max_length=150, disabled=True)
    first_name = forms.CharField(max_length=150, required=False, disabled=True)
    last_name = forms.CharField(max_length=150, required=False, disabled=True)
    email = forms.EmailField(max_length=100, required=False, disabled=True)
    source = forms.CharField(max_length=16, disabled=True)
    is_external = forms.BooleanField(required=False, disabled=True)
    role = forms.ModelChoiceField(
        queryset=ProjectUserRoleChoice.objects.all(), empty_label=None)
    selected = forms.BooleanField(initial=False, required=False)


class ProjectReactivateUserForm(forms.Form):
    username = forms.CharField(max_length=150, disabled=True)
    first_name = forms.CharField(max_length=150, required=False, disabled=True)
    last_name = forms.CharField(max_length=150, required=False, disabled=True)
    email = forms.EmailField(max_length=100, required=False, disabled=True)
    role = forms.ModelChoiceField(
        queryset=ProjectUserRoleChoice.objects.all(), required=False, empty_label=None)
    selected = forms.BooleanField(initial=False, required=False)


class ProjectAddUsersToAllocationForm(forms.Form):
    allocation = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple(attrs={'checked': 'checked'}), required=False)

    def __init__(self, request_user, project_pk, *args, **kwargs):
        super().__init__(*args, **kwargs)
        project_obj = get_object_or_404(Project, pk=project_pk)

        allocation_query_set = project_obj.allocation_set.filter(
            resources__is_allocatable=True, is_locked=False,
            status__name__in=PENDING_ACTIVE_ALLOCATION_STATUSES
        ).distinct()
        allocation_choices = [(
            allocation.id, "%s (%s) %s" % (
                allocation.get_parent_resource.name,
                allocation.get_parent_resource.resource_type.name,
                allocation.description if allocation.description else ''
            )
        ) for allocation in allocation_query_set]

        allocation_choices_sorted = []
        allocation_choices_sorted = sorted(allocation_choices, key=lambda x: x[1][0].lower())
        allocation_choices.insert(0, ('__select_all__', 'Select All'))
        if allocation_query_set:
            self.fields['allocation'].choices = allocation_choices_sorted
            self.fields['allocation'].help_text = '<br/>Select allocations to add selected users to.'
        else:
            self.fields['allocation'].widget = forms.HiddenInput()


class ProjectRemoveUserForm(forms.Form):
    username = forms.CharField(max_length=150, disabled=True)
    first_name = forms.CharField(max_length=150, required=False, disabled=True)
    last_name = forms.CharField(max_length=150, required=False, disabled=True)
    email = forms.EmailField(max_length=100, required=False, disabled=True)
    role = forms.CharField(max_length=30, disabled=True)
    primary_group = forms.BooleanField(required=False, disabled=True)
    is_external = forms.BooleanField(required=False, disabled=True)
    selected = forms.BooleanField(initial=False, required=False)


class ProjectUserUpdateForm(forms.Form):
    role = forms.ModelChoiceField(
        queryset=ProjectUserRoleChoice.objects.exclude(name='PI'), empty_label=None)
    enable_notifications = forms.BooleanField(initial=False, required=False)
    expiration = forms.DateField(
        label='Account Expiration',
        required=False,
        # type="date" inputs only accept ISO dates; pinning the format keeps the current
        # value visible in any locale (a blank field would clear the expiration on save).
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}),
    )

    def __init__(self, request_user, project_pk, *args, **kwargs):
        """If user is not PI or Admin, only show Access Manager, Storage Manager, and User roles.

        How the expiration can be edited depends on values the view passes in `initial`:
        - primary_group: the date is only editable from the user's primary project;
          elsewhere the field is removed.
        - account_type: the user's ACCOUNT_TYPE_GROUPS preset, or None. Its
          expiration_max_days limits the date and expiration_required makes it required.
          With no limit, the date is optional and uncapped.
        """
        super().__init__(*args, **kwargs)
        project_obj = get_object_or_404(Project, pk=project_pk)
        roles = ProjectUserRoleChoice.objects.exclude(name='PI')
        if not project_obj.pi == request_user and not request_user.is_superuser:
            self.fields['role'].queryset = roles.exclude(name='General Manager')

        preset = self.initial.get('account_type') or {}
        # How far out the expiration can be set; None means no limit.
        self.max_days = preset.get('expiration_max_days')

        if not self.initial.get('primary_group'):
            del self.fields['expiration']
        elif self.max_days is not None:
            self.fields['expiration'].required = preset.get('expiration_required', False)
            # Limit the browser's date picker to the dates clean_expiration accepts.
            today = timezone.localdate()
            self.fields['expiration'].widget.attrs.update({
                'min': (today + datetime.timedelta(days=1)).isoformat(),
                'max': (today + datetime.timedelta(days=self.max_days)).isoformat(),
            })
            self.fields['expiration'].help_text = (
                    # f'Required for external accounts. '
                f'Must be no more than {self.max_days} days from today.'
            )
        else:
            self.fields['expiration'].help_text = 'Optional. Leave blank for an account that never expires.'

    def clean_expiration(self):
        """Validate the expiration date.

        Users with a limit (self.max_days, from their account-type presets): the date must
        be in the future and no more than self.max_days from today on every save, even if
        unchanged.
        Others: blank clears the expiration, an unchanged date is accepted as is,
        and a new date only has to be in the future.
        """
        new_date = self.cleaned_data.get('expiration')
        if new_date is None:
            # Blank: required=True already rejects this for external users.
            return None
        if self.max_days is None and new_date == self.initial.get('expiration'):
            return new_date

        today = timezone.localdate()
        if new_date <= today:
            raise forms.ValidationError('Expiration date must be in the future.')
        if self.max_days is None:
            return new_date
        max_date = today + datetime.timedelta(days=self.max_days)
        if new_date > max_date:
            raise forms.ValidationError(
                f'Expiration date cannot be more than {self.max_days} days '
                f'from today ({max_date:%Y-%m-%d}).'
            )
        return new_date


class ProjectReviewForm(forms.Form):
    reason = forms.CharField(label='Reason for not updating project information', widget=forms.Textarea(attrs={
                             'placeholder': 'If you have no new information to provide, you are required to provide a statement explaining this in this box. Thank you!'}), required=False)
    acknowledgement = forms.BooleanField(
        label='By checking this box I acknowledge that I have updated my project to the best of my knowledge', initial=False, required=True)

    def __init__(self, project_pk, *args, **kwargs):
        super().__init__(*args, **kwargs)
        project_obj = get_object_or_404(Project, pk=project_pk)
        now = datetime.datetime.now(datetime.timezone.utc)

        if project_obj.grant_set.exists():
            latest_grant = project_obj.grant_set.order_by('-modified')[0]
            grant_updated_in_last_year = (
                now - latest_grant.created).days < 365
        else:
            grant_updated_in_last_year = None

        if project_obj.publication_set.exists():
            latest_publication = project_obj.publication_set.order_by(
                '-created')[0]
            publication_updated_in_last_year = (
                now - latest_publication.created).days < 365
        else:
            publication_updated_in_last_year = None

        if grant_updated_in_last_year or publication_updated_in_last_year:
            self.fields['reason'].widget = forms.HiddenInput()
        else:
            self.fields['reason'].required = True


class ProjectReviewEmailForm(forms.Form):
    cc = forms.CharField(
        required=False
    )
    email_body = forms.CharField(
        required=True,
        widget=forms.Textarea
    )

    def __init__(self, pk, *args, **kwargs):
        super().__init__(*args, **kwargs)
        project_review_obj = get_object_or_404(ProjectReview, pk=int(pk))
        self.fields['email_body'].initial = 'Dear {} {} \n{}'.format(
            project_review_obj.project.pi.first_name, project_review_obj.project.pi.last_name, EMAIL_DIRECTOR_PENDING_PROJECT_REVIEW_EMAIL)
        self.fields['cc'].initial = ', '.join(
            [EMAIL_DIRECTOR_EMAIL_ADDRESS] + EMAIL_ADMIN_LIST)

class ProjectAttributeAddForm(forms.ModelForm):
    class Meta:
        fields = '__all__'
        model = ProjectAttribute
        labels = {
            'proj_attr_type' : "Project Attribute Type",
        }

    def __init__(self, *args, **kwargs):
        super(ProjectAttributeAddForm, self).__init__(*args, **kwargs)
        user =(kwargs.get('initial')).get('user')
        self.fields['proj_attr_type'].queryset = self.fields['proj_attr_type'].queryset.order_by(Lower('name'))
        if not user.is_superuser:
            self.fields['proj_attr_type'].queryset = self.fields['proj_attr_type'].queryset.filter(is_private=False)

class ProjectAttributeDeleteForm(forms.Form):
    pk = forms.IntegerField(required=False, disabled=True)
    name = forms.CharField(max_length=150, required=False, disabled=True)
    attr_type = forms.CharField(max_length=150, required=False, disabled=True)
    value = forms.CharField(max_length=150, required=False, disabled=True)
    selected = forms.BooleanField(initial=False, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['pk'].widget = forms.HiddenInput()

# class ProjectAttributeChangeForm(forms.Form):
#     pk = forms.IntegerField(required=False, disabled=True)
#     name = forms.CharField(max_length=150, required=False, disabled=True)
#     value = forms.CharField(max_length=150, required=False, disabled=True)
#     new_value = forms.CharField(max_length=150, required=False, disabled=False)

#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.fields['pk'].widget = forms.HiddenInput()

#     def clean(self):
#         cleaned_data = super().clean()

#         if cleaned_data.get('new_value') != "":
#             proj_attr = ProjectAttribute.objects.get(pk=cleaned_data.get('pk'))
#             proj_attr.value = cleaned_data.get('new_value')
#             proj_attr.clean()


class ProjectAttributeUpdateForm(forms.Form):
    pk = forms.IntegerField(required=False, disabled=True)
    new_value = forms.CharField(max_length=150, required=True, disabled=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['pk'].widget = forms.HiddenInput()

    def clean(self):
        cleaned_data = super().clean()

        if cleaned_data.get('new_value') != "":
            proj_attr = ProjectAttribute.objects.get(pk=cleaned_data.get('pk'))
            proj_attr.value = cleaned_data.get('new_value')
            proj_attr.clean()


class ProjectOffboardingSelectForm(forms.Form):
    project = forms.ModelChoiceField(queryset=Project.objects.none(), empty_label=None)

    def __init__(self, request_user, *args, **kwargs):
        """Offer New/Active projects: the requesting user's own, or every one for a superuser."""
        super().__init__(*args, **kwargs)
        projects = Project.objects.filter(status__name__in=['New', 'Active'])
        if request_user.is_superuser:
            projects = projects.select_related('pi')
            self.fields['project'].label_from_instance = lambda p: f'{p.title} (PI: {p.pi.username})'
        else:
            projects = projects.filter(pi=request_user)
        self.fields['project'].queryset = projects.order_by('title')


RETENTION_UNITS = (('days', 'days'), ('weeks', 'weeks'), ('months', 'months'), ('years', 'years'))


# Longest allowed retention (10 years), expressed in each unit.
RETENTION_MAXIMUMS = {'days': 3650, 'weeks': 521, 'months': 120, 'years': 10}


class RetentionDurationWidget(forms.MultiWidget):
    """Number input next to a unit drop-down."""

    def __init__(self, attrs=None):
        widgets = [
            forms.NumberInput(attrs={'min': 1, 'class': 'form-control', 'style': 'max-width: 8rem'}),
            forms.Select(choices=RETENTION_UNITS, attrs={'class': 'form-control', 'style': 'max-width: 10rem'}),
        ]
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if value:
            number, _, unit = str(value).partition(' ')
            return [number, unit if unit.endswith('s') else unit + 's']
        return [None, 'years']

    def render(self, name, value, attrs=None, renderer=None):
        # lay the two inputs out side by side
        html = super().render(name, value, attrs, renderer)
        return mark_safe(f'<div class="form-inline">{html}</div>')


class RetentionDurationField(forms.MultiValueField):
    """A positive whole number plus a unit (days/weeks/months/years); cleans to e.g. "10 years"."""
    widget = RetentionDurationWidget

    def __init__(self, **kwargs):
        fields = (
            forms.IntegerField(min_value=1, required=False),
            forms.ChoiceField(choices=RETENTION_UNITS, required=False),
        )
        super().__init__(fields=fields, require_all_fields=False, required=False, **kwargs)

    def compress(self, data_list):
        if not data_list or not data_list[0]:
            return ''
        number, unit = data_list[0], data_list[1] or 'years'
        if number > RETENTION_MAXIMUMS[unit]:
            raise forms.ValidationError(
                'The maximum retention time is 10 years (120 months, 521 weeks, or 3650 days).')
        return f'{number} {unit[:-1] if number == 1 else unit}'


OFFBOARDING_ALLOCATION_FIELD_LABELS = {
    'action': 'How should this allocation be handled?',
    'retain_duration': 'How long does the data need to be retained?',
    'retain_contact_name': 'Department contact name',
    'retain_contact_email': 'Department contact email',
    'retain_billing_code': '33-digit billing/funding code',
    'move_within_harvard': 'Are you migrating the data to another group or storage location at Harvard?',
    'move_recipient': 'Recipient group or contact at Harvard',
    'move_destination': 'Destination outside Harvard',
}


def offboarding_date_limit(today=None):
    """Latest allowed offboarding date: two years from today."""
    today = today or datetime.date.today()
    try:
        return today.replace(year=today.year + 2)
    except ValueError:  # Feb 29 -> Feb 28
        return today.replace(year=today.year + 2, day=28)


class ProjectOffboardingForm(forms.Form):
    """Offboarding questionnaire for a project: storage disposition per active
    storage allocation and account disposition per active group member.
    """
    YES_NO = (('yes', 'Yes'), ('no', 'No'))
    MEMBER_STATUSES = (
        ('offboard', 'Fully offboard'),
        ('sponsor', 'New sponsor'),
    )
    ALLOCATION_ACTIONS = (
        ('retain', 'Retain the allocation in its current storage location'),
        ('delete', 'Delete the allocation'),
        ('move', 'Move the allocation'),
    )

    alternative_email = forms.EmailField(required=False, label='Alternative email')
    offboarding_date = forms.DateField(
        label='Date project will be completed or when leaving the university',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )

    def __init__(self, project_pk, *args, **kwargs):
        super().__init__(*args, **kwargs)
        project_obj = get_object_or_404(Project, pk=project_pk)
        self.project = project_obj
        self.fields['offboarding_date'].widget.attrs['max'] = offboarding_date_limit().isoformat()

        self.allocations = list(project_obj.allocation_set.filter(
            status__name='Active', resources__resource_type__name='Storage'
        ).distinct().order_by('resources__name'))
        # only members whose primary group is this project need an offboarding decision
        self.members = list(ProjectUser.objects.filter(
            project=project_obj, status__name='Active', primary_group=True
        ).exclude(user=project_obj.pi).select_related('user').order_by('user__username'))

        for allocation in self.allocations:
            self._add_allocation_fields(allocation)
        for project_user in self.members:
            self.fields[f'status_{project_user.pk}'] = forms.ChoiceField(
                choices=self.MEMBER_STATUSES, widget=forms.RadioSelect)
            self.fields[f'sponsor_{project_user.pk}'] = forms.CharField(
                label='Name of new sponsor', required=False, max_length=255)

    @staticmethod
    def allocation_prefix(allocation):
        return f'alloc_{allocation.pk}_'

    @staticmethod
    def allocation_path(allocation):
        try:
            return allocation.path or str(allocation.get_parent_resource)
        except Exception:  # noqa: BLE001 - missing 'Subdirectory' attribute type, etc.
            return str(allocation.get_parent_resource)

    def _add_allocation_fields(self, allocation):
        p = self.allocation_prefix(allocation)
        labels = OFFBOARDING_ALLOCATION_FIELD_LABELS
        radio = forms.RadioSelect
        # retain/delete/move are mutually exclusive, so they are a single required choice.
        self.fields[p + 'action'] = forms.ChoiceField(
            label=labels['action'], choices=self.ALLOCATION_ACTIONS, widget=radio)
        self.fields[p + 'retain_duration'] = RetentionDurationField(label=labels['retain_duration'])
        self.fields[p + 'retain_contact_name'] = forms.CharField(
            label=labels['retain_contact_name'], required=False, max_length=255)
        self.fields[p + 'retain_contact_email'] = forms.EmailField(
            label=labels['retain_contact_email'], required=False)
        self.fields[p + 'retain_billing_code'] = ExpenseCodeField(
            label=labels['retain_billing_code'], required=False)
        self.fields[p + 'move_within_harvard'] = forms.ChoiceField(
            label=labels['move_within_harvard'], choices=self.YES_NO, widget=radio, required=False)
        self.fields[p + 'move_recipient'] = forms.CharField(
            label=labels['move_recipient'], required=False)
        self.fields[p + 'move_destination'] = forms.CharField(
            label=labels['move_destination'], required=False)

    def allocation_rows(self):
        """Bound fields grouped per allocation, for template rendering."""
        rows = []
        for allocation in self.allocations:
            p = self.allocation_prefix(allocation)
            rows.append({
                'allocation': allocation,
                'path': self.allocation_path(allocation),
                'resource': allocation.get_parent_resource,
                'prefix': p,
                **{name: self[p + name] for name in OFFBOARDING_ALLOCATION_FIELD_LABELS},
            })
        return rows

    def member_rows(self):
        return [
            {
                'project_user': project_user,
                'status': self[f'status_{project_user.pk}'],
                'sponsor': self[f'sponsor_{project_user.pk}'],
            }
            for project_user in self.members
        ]

    def clean_offboarding_date(self):
        date = self.cleaned_data['offboarding_date']
        limit = offboarding_date_limit()
        if date > limit:
            raise forms.ValidationError(
                f'The expected date of offboarding cannot be more than two years from today '
                f'(latest allowed: {limit.isoformat()}).')
        return date

    def clean(self):
        cleaned_data = super().clean()
        required_msg = 'This field is required.'
        for allocation in self.allocations:
            p = self.allocation_prefix(allocation)
            action = cleaned_data.get(p + 'action')
            if action == 'retain':
                for name in ('retain_duration', 'retain_contact_name', 'retain_contact_email',
                             'retain_billing_code'):
                    if not cleaned_data.get(p + name, '').strip() and not self.has_error(p + name):
                        self.add_error(p + name, required_msg)
                code = cleaned_data.get(p + 'retain_billing_code', '')
                if code and not self.has_error(p + 'retain_billing_code'):
                    digits = re.sub(r'[^0-9xX]', '', code)
                    cleaned_data[p + 'retain_billing_code'] = '-'.join(
                        [digits[:3], digits[3:8], digits[8:12], digits[12:18], digits[18:24], digits[24:28], digits[28:33]])
            if action == 'move':
                within = cleaned_data.get(p + 'move_within_harvard')
                if not within:
                    self.add_error(p + 'move_within_harvard', required_msg)
                elif within == 'yes' and not cleaned_data.get(p + 'move_recipient', '').strip():
                    self.add_error(p + 'move_recipient', required_msg)
                elif within == 'no' and not cleaned_data.get(p + 'move_destination', '').strip():
                    self.add_error(p + 'move_destination', required_msg)
        for project_user in self.members:
            status = cleaned_data.get(f'status_{project_user.pk}')
            sponsor_field = f'sponsor_{project_user.pk}'
            if status == 'sponsor' and not cleaned_data.get(sponsor_field, '').strip() \
                    and not self.has_error(sponsor_field):
                self.add_error(
                    sponsor_field, 
                    'Please provide the name of the new sponsor, or TBD if not yet known.'
                )
            elif status == 'offboard':
                cleaned_data[sponsor_field] = ''
        return cleaned_data

    def email_context(self, user):
        """Context for the email/project_offboarding.txt template.

        Flattens the per-allocation and per-member fields (whose names are
        computed from pks) into lists the template can iterate over.
        """
        cleaned_data = self.cleaned_data
        allocations = []
        for allocation in self.allocations:
            p = self.allocation_prefix(allocation)
            allocations.append({
                'pk': allocation.pk,
                'path': self.allocation_path(allocation),
                'retain': cleaned_data[p + 'action'] == 'retain',
                'retain_duration': cleaned_data[p + 'retain_duration'],
                'retain_contact_name': cleaned_data[p + 'retain_contact_name'],
                'retain_contact_email': cleaned_data[p + 'retain_contact_email'],
                'retain_billing_code': cleaned_data[p + 'retain_billing_code'],
                'delete': cleaned_data[p + 'action'] == 'delete',
                'move': cleaned_data[p + 'action'] == 'move',
                'move_within_harvard': cleaned_data[p + 'move_within_harvard'] == 'yes',
                'move_recipient': cleaned_data[p + 'move_recipient'],
                'move_destination': cleaned_data[p + 'move_destination'],
            })
        members = [
            {
                'username': project_user.user.username,
                'full_name': project_user.user.get_full_name(),
                'email': project_user.user.email,
                'offboard': cleaned_data[f'status_{project_user.pk}'] == 'offboard',
                'sponsor': cleaned_data[f'sponsor_{project_user.pk}'].strip(),
            }
            for project_user in self.members
        ]
        return {
            'submitter': user,
            'project': self.project,
            'alternative_email': cleaned_data.get('alternative_email'),
            'offboarding_date': cleaned_data['offboarding_date'],
            'allocations': allocations,
            'members': members,
        }
