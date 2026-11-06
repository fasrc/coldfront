import logging
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from coldfront.core.project.models import ProjectStatusChoice
from coldfront.core.test_helpers.factories import (
    ProjectFactory, ProjectUserFactory, UserFactory, setup_models,
)

logging.disable(logging.CRITICAL)

UTIL_FIXTURES = [
    "coldfront/core/test_helpers/test_data/test_fixtures/ifx.json",
]
SUCCESS_MESSAGE = 'Offboarding form sent.'


def enable_email(test_func):
    """mail.EMAIL_ENABLED and views.EMAIL_SENDER are read at import time, so
    override_settings can't change them; patch them as core/utils/tests.py does."""
    test_func = patch('coldfront.core.utils.mail.EMAIL_ENABLED', True)(test_func)
    test_func = patch('coldfront.core.project.views.EMAIL_SENDER', 'coldfront@example.edu')(test_func)
    return override_settings(EMAIL_TICKET_SYSTEM_ADDRESS='tickets@example.edu')(test_func)


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
        ProjectUserFactory(user=cls.member, project=cls.project)
        cls.admin = UserFactory(username='admin_off', is_superuser=True)

    def form_url(self):
        return reverse('project-offboarding', kwargs={'pk': self.project.pk})

    def valid_data(self, **extra):
        data = {
            'offboarding_date': '2030-01-01',
            f'offboard_{self.project.projectuser_set.get(user=self.member).pk}': 'on',
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
        data = {'offboarding_date': '2030-01-01', f'sponsor_{member_pk}': 'Smith & Jones <Lab>'}
        self.client.post(self.form_url(), data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('staying; new sponsor: Smith & Jones <Lab>', mail.outbox[0].body)

    @override_settings(EMAIL_TICKET_SYSTEM_ADDRESS='')
    def test_missing_ticket_address_does_not_claim_success(self):
        self.client.force_login(self.pi)
        resp = self.client.post(self.form_url(), self.valid_data(), follow=True)
        self.assertNotContains(resp, SUCCESS_MESSAGE)

    def test_date_required(self):
        self.client.force_login(self.pi)
        resp = self.client.post(self.form_url(), {})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('offboarding_date', resp.context['form'].errors)


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
