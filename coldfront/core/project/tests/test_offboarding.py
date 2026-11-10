import logging
from unittest.mock import patch

from django.core import mail
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from coldfront.core.project.models import ProjectStatusChoice
from coldfront.core.project.forms import ProjectOffboardingForm
from coldfront.core.test_helpers.factories import (
    AllocationFactory, ResourceFactory, ResourceTypeFactory, ProjectFactory, ProjectUserFactory, UserFactory, setup_models,
)

logging.disable(logging.CRITICAL)

UTIL_FIXTURES = [
    "coldfront/core/test_helpers/test_data/test_fixtures/ifx.json",
]
SUCCESS_MESSAGE = 'Offboarding form sent.'


def enable_email(test_func):
    """mail.EMAIL_ENABLED, views.EMAIL_SENDER and views.EMAIL_TICKET_SYSTEM_ADDRESS are read at import time, so
    override_settings can't change them; patch them as core/utils/tests.py does."""
    test_func = patch('coldfront.core.utils.mail.EMAIL_ENABLED', True)(test_func)
    test_func = patch('coldfront.core.project.views.EMAIL_SENDER', 'coldfront@example.edu')(test_func)
    return patch('coldfront.core.project.views.EMAIL_TICKET_SYSTEM_ADDRESS', 'tickets@example.edu')(test_func)


class OffboardingTests(TestCase):
    fixtures = UTIL_FIXTURES

    @classmethod
    def setUpTestData(cls):
        setup_models(cls)
        cls.pi = UserFactory(username='pi_off', email='pi@example.edu')
        cls.pi.userprofile.is_pi = True
        cls.pi.userprofile.save()
        cls.project = ProjectFactory(pi=cls.pi, title='off_lab')
        cls.other = UserFactory(username='other_pi')
        cls.other.userprofile.is_pi = True
        cls.other.userprofile.save()
        cls.member = UserFactory(username='member1')
        ProjectUserFactory(user=cls.member, project=cls.project, primary_group=True)
        cls.admin = UserFactory(username='admin_off', is_superuser=True)

    def form_url(self):
        return reverse('project-offboarding', kwargs={'pk': self.project.pk})

    def valid_data(self, **extra):
        data = {
            'offboarding_date': '2030-01-01',
            f'status_{self.project.projectuser_set.get(user=self.member).pk}': 'offboard',
        }
        data.update(extra)
        return data

    def test_navbar_shows_management_for_pi_only(self):
        self.client.force_login(self.pi)
        self.assertContains(self.client.get('/'), 'Request Project Decommission')
        self.client.force_login(self.member)
        self.assertNotContains(self.client.get('/'), 'Request Project Decommission')

    def test_select_redirects_to_form(self):
        self.client.force_login(self.pi)
        resp = self.client.post(reverse('project-offboarding-select'), {'project': self.project.pk})
        self.assertRedirects(resp, self.form_url(), fetch_redirect_response=False)

    def test_non_pi_denied(self):
        self.client.force_login(self.member)
        self.assertNotEqual(self.client.get(reverse('project-offboarding-select')).status_code, 200)

    def test_other_pi_cannot_offboard_project(self):
        self.client.force_login(self.other)
        self.assertNotEqual(self.client.get(self.form_url()).status_code, 200)

    def test_admin_can_open_form_go_back_to_project(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.form_url())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['select_url'], reverse('project-detail', kwargs={'pk': self.project.pk}))

    def test_detail_button_visible_to_pi_and_admin_only(self):
        detail_url = reverse('project-detail', kwargs={'pk': self.project.pk})
        for user, visible in ((self.pi, True), (self.admin, True), (self.member, False)):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                resp = self.client.get(detail_url)
                self.assertEqual(resp.status_code, 200)
                # Match the button id: PIs also see the same text in the navbar.
                if visible:
                    self.assertContains(resp, 'id="request-decommission"')
                else:
                    self.assertNotContains(resp, 'id="request-decommission"')

    @enable_email
    def test_submit_sends_email_and_redirects(self):
        self.client.force_login(self.pi)
        self.assertEqual(self.client.get(self.form_url()).status_code, 200)
        resp = self.client.post(self.form_url(), self.valid_data(), follow=True)
        self.assertRedirects(resp, reverse('home'))
        self.assertContains(resp, SUCCESS_MESSAGE)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['tickets@example.edu'])
        self.assertIn('off_lab', mail.outbox[0].body)
        self.assertIn('fully offboard', mail.outbox[0].body)

    @enable_email
    def test_email_free_text_not_html_escaped(self):
        self.client.force_login(self.pi)
        member_pk = self.project.projectuser_set.get(user=self.member).pk
        data = {'offboarding_date': '2030-01-01', f'status_{member_pk}': 'sponsor',
                f'sponsor_{member_pk}': 'Smith & Jones <Lab>'}
        self.client.post(self.form_url(), data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('staying; new sponsor: Smith & Jones <Lab>', mail.outbox[0].body)

    def test_member_status_required(self):
        self.client.force_login(self.pi)
        member_pk = self.project.projectuser_set.get(user=self.member).pk
        resp = self.client.post(self.form_url(), {'offboarding_date': '2030-01-01'})
        self.assertIn(f'status_{member_pk}', resp.context['form'].errors)

    def test_new_sponsor_requires_name(self):
        self.client.force_login(self.pi)
        member_pk = self.project.projectuser_set.get(user=self.member).pk
        for sponsor in ('', '   '):
            resp = self.client.post(self.form_url(), {
                'offboarding_date': '2030-01-01', f'status_{member_pk}': 'sponsor',
                f'sponsor_{member_pk}': sponsor})
            self.assertIn(f'sponsor_{member_pk}', resp.context['form'].errors)

    @enable_email
    def test_offboard_status_needs_no_sponsor(self):
        self.client.force_login(self.pi)
        resp = self.client.post(self.form_url(), self.valid_data())
        self.assertRedirects(resp, reverse('home'), fetch_redirect_response=False)

    def test_only_primary_group_members_listed(self):
        non_primary = UserFactory(username='not_primary')
        ProjectUserFactory(user=non_primary, project=self.project, primary_group=False)
        self.client.force_login(self.pi)
        members = [row['project_user'].user for row in self.client.get(self.form_url()).context['member_rows']]
        self.assertEqual(members, [self.member])

    def test_date_required(self):
        self.client.force_login(self.pi)
        resp = self.client.post(self.form_url(), {})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('offboarding_date', resp.context['form'].errors)


class OffboardingStorageChoiceTests(TestCase):
    """Per storage allocation, exactly one of retain/delete/move must be "yes"."""
    fixtures = UTIL_FIXTURES

    @classmethod
    def setUpTestData(cls):
        setup_models(cls)
        cls.pi = UserFactory(username='pi_storage')
        cls.pi.userprofile.is_pi = True
        cls.pi.userprofile.save()
        cls.project = ProjectFactory(pi=cls.pi, title='storage_lab')
        cls.allocation = AllocationFactory(project=cls.project)
        cls.allocation.resources.add(ResourceFactory(resource_type=ResourceTypeFactory(name='Storage')))
        cls.prefix = f'alloc_{cls.allocation.pk}_'

    def build_form(self, **answers):
        data = {'offboarding_date': '2030-01-01'}
        data.update({self.prefix + k: v for k, v in answers.items()})
        return ProjectOffboardingForm(self.project.pk, data)

    def test_allocation_listed(self):
        self.assertEqual(self.build_form().allocations, [self.allocation])

    def test_none_answered_invalid(self):
        form = self.build_form()
        self.assertFalse(form.is_valid())
        self.assertIn(self.prefix + 'action', form.errors)

    def test_unknown_action_invalid(self):
        self.assertFalse(self.build_form(action='keep').is_valid())

    def test_delete_valid(self):
        form = self.build_form(action='delete')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.email_context(self.pi)['allocations'][0]['retain'])
        self.assertTrue(form.email_context(self.pi)['allocations'][0]['delete'])

    def test_only_selected_option_subfields_required(self):
        # blank retain/move sub-fields don't matter when "delete" is chosen
        self.assertTrue(self.build_form(action='delete', retain_duration_0='').is_valid())

    def test_move_requires_within_harvard_answer_and_destination(self):
        self.assertIn(self.prefix + 'move_within_harvard', self.build_form(action='move').errors)
        self.assertIn(
            self.prefix + 'move_recipient',
            self.build_form(action='move', move_within_harvard='yes').errors)
        self.assertIn(
            self.prefix + 'move_destination',
            self.build_form(action='move', move_within_harvard='no').errors)
        self.assertTrue(self.build_form(
            action='move', move_within_harvard='no', move_destination='Dataverse').is_valid())

    def retain_answers(self, **extra):
        answers = {
            'action': 'retain', 'retain_duration_0': '2', 'retain_duration_1': 'years',
            'retain_contact_name': 'Dept Admin', 'retain_contact_email': 'admin@example.edu',
            'retain_billing_code': '1' * 33,
        }
        answers.update(extra)
        return answers

    def test_retain_requires_duration_contact_and_billing_code(self):
        form = self.build_form(action='retain')
        self.assertFalse(form.is_valid())
        for name in ('retain_duration', 'retain_contact_name', 'retain_contact_email', 'retain_billing_code'):
            self.assertIn(self.prefix + name, form.errors)

    def test_retain_valid_formats_billing_code_with_dashes(self):
        form = self.build_form(**self.retain_answers(retain_billing_code='123-45678-9012-345678-901234-5678-90123'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data[self.prefix + 'retain_billing_code'], '123-45678-9012-345678-901234-5678-90123')

    def test_billing_code_wrong_length_invalid(self):
        form = self.build_form(**self.retain_answers(retain_billing_code='123-456'))
        self.assertFalse(form.is_valid())
        self.assertIn(self.prefix + 'retain_billing_code', form.errors)

    def test_billing_code_x_only_allowed_in_product_code(self):
        form = self.build_form(**self.retain_answers(retain_billing_code='x' + '1' * 32))
        self.assertFalse(form.is_valid())
        self.assertIn(self.prefix + 'retain_billing_code', form.errors)
        ok = self.build_form(**self.retain_answers(retain_billing_code='1' * 8 + 'xxxx' + '1' * 21))
        self.assertTrue(ok.is_valid(), ok.errors)

    def test_contact_email_must_be_valid(self):
        form = self.build_form(**self.retain_answers(retain_contact_email='not-an-email'))
        self.assertFalse(form.is_valid())
        self.assertIn(self.prefix + 'retain_contact_email', form.errors)

    def render_email(self, **answers):
        form = self.build_form(**answers)
        self.assertTrue(form.is_valid(), form.errors)
        return render_to_string('email/project_offboarding.txt', form.email_context(self.pi))

    def test_email_plan_line_retain(self):
        body = self.render_email(**self.retain_answers())
        self.assertIn('    Plan: Retain in current location\n      Retention period: 2 years\n', body)
        self.assertIn('      Department contact: Dept Admin <admin@example.edu>\n', body)
        self.assertNotIn('Delete:', body)
        self.assertNotIn('Move:', body)

    def test_email_plan_line_delete(self):
        body = self.render_email(action='delete')
        self.assertIn(f'(id {self.allocation.pk})\n    Plan: Delete\n', body)
        self.assertNotIn('Retention period', body)

    def test_email_plan_line_move(self):
        body = self.render_email(action='move', move_within_harvard='no', move_destination='Dataverse')
        self.assertIn('    Plan: Move\n      Moving outside Harvard to: Dataverse\n', body)

    def test_retention_duration_combines_number_and_unit(self):
        for number, unit, expected in (('10', 'years', '10 years'), ('1', 'months', '1 month'),
                                       ('3', 'weeks', '3 weeks'), ('30', 'days', '30 days')):
            form = self.build_form(**self.retain_answers(retain_duration_0=number, retain_duration_1=unit))
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.cleaned_data[self.prefix + 'retain_duration'], expected)

    def test_retention_duration_maximum(self):
        for number, unit in (('10', 'years'), ('120', 'months'), ('521', 'weeks'), ('3650', 'days')):
            with self.subTest(number=number, unit=unit, ok=True):
                form = self.build_form(**self.retain_answers(retain_duration_0=number, retain_duration_1=unit))
                self.assertTrue(form.is_valid(), form.errors)
        for number, unit in (('11', 'years'), ('121', 'months'), ('522', 'weeks'), ('3651', 'days')):
            with self.subTest(number=number, unit=unit, ok=False):
                form = self.build_form(**self.retain_answers(retain_duration_0=number, retain_duration_1=unit))
                self.assertIn(self.prefix + 'retain_duration', form.errors)

    def test_retention_duration_invalid(self):
        for number, unit in (('0', 'years'), ('-2', 'years'), ('1.5', 'years'), ('abc', 'days'),
                             ('2', 'decades'), ('', 'years')):
            with self.subTest(number=number, unit=unit):
                form = self.build_form(**self.retain_answers(retain_duration_0=number, retain_duration_1=unit))
                self.assertIn(self.prefix + 'retain_duration', form.errors)

    def test_billing_code_label(self):
        label = self.build_form()[self.prefix + 'retain_billing_code'].label
        self.assertEqual(label, '33-digit billing/funding code')


class ProjectDetailManageButtonsTests(TestCase):
    """Manage Project card: superusers get every button; a project's PI gets only
    Request Project Decommission; other users don't see the card."""
    fixtures = UTIL_FIXTURES

    @classmethod
    def setUpTestData(cls):
        setup_models(cls)
        cls.pi = UserFactory(username='pi_manage')
        cls.pi.userprofile.is_pi = True
        cls.pi.userprofile.save()
        cls.project = ProjectFactory(pi=cls.pi, title='manage_lab')
        cls.member = UserFactory(username='member_manage')
        ProjectUserFactory(user=cls.member, project=cls.project)
        cls.admin = UserFactory(username='admin_manage', is_superuser=True)

    def get_detail(self, user):
        self.client.force_login(user)
        resp = self.client.get(reverse('project-detail', kwargs={'pk': self.project.pk}))
        self.assertEqual(resp.status_code, 200)
        return resp

    def href(self, url_name):
        return f'href="{reverse(url_name, kwargs={"pk": self.project.pk})}"'

    def archive_project(self):
        self.project.status = ProjectStatusChoice.objects.get(name='Archived')
        self.project.save()

    def test_pi_sees_manage_card_with_decommission_button(self):
        resp = self.get_detail(self.pi)
        self.assertContains(resp, 'id="manage-project"')
        self.assertContains(resp, 'id="request-decommission"')
        self.assertContains(resp, self.href('project-offboarding'))

    def test_pi_does_not_see_admin_manage_buttons(self):
        resp = self.get_detail(self.pi)
        self.assertNotContains(resp, self.href('project-update'))
        self.assertNotContains(resp, self.href('project-archive'))
        self.assertNotContains(resp, self.href('project-unarchive'))

    def test_admin_sees_all_manage_buttons(self):
        resp = self.get_detail(self.admin)
        self.assertContains(resp, self.href('project-update'))
        self.assertContains(resp, self.href('project-archive'))
        self.assertContains(resp, 'id="request-decommission"')

    def test_member_does_not_see_manage_card(self):
        resp = self.get_detail(self.member)
        self.assertNotContains(resp, 'id="manage-project"')
        self.assertNotContains(resp, 'id="request-decommission"')

    def test_pi_does_not_see_manage_card_on_archived_project(self):
        self.archive_project()
        resp = self.get_detail(self.pi)
        self.assertNotContains(resp, 'id="manage-project"')
        self.assertNotContains(resp, self.href('project-unarchive'))

    def test_admin_sees_reactivate_on_archived_project(self):
        self.archive_project()
        resp = self.get_detail(self.admin)
        self.assertContains(resp, self.href('project-unarchive'))
        self.assertNotContains(resp, 'id="request-decommission"')
