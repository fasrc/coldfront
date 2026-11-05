import logging

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from coldfront.core.test_helpers.factories import (
    ProjectFactory, ProjectUserFactory, UserFactory, setup_models,
)

logging.disable(logging.CRITICAL)

UTIL_FIXTURES = [
    "coldfront/core/test_helpers/test_data/test_fixtures/ifx.json",
]


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
        self.assertContains(self.client.get('/'), 'Decommission a Project')
        self.client.force_login(self.member)
        self.assertNotContains(self.client.get('/'), 'Decommission a Project')

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

    @override_settings(EMAIL_TICKET_SYSTEM_ADDRESS='tickets@example.edu', EMAIL_ENABLED=True)
    def test_submit_sends_email_and_redirects(self):
        self.client.force_login(self.pi)
        self.assertEqual(self.client.get(self.form_url()).status_code, 200)
        resp = self.client.post(self.form_url(), self.valid_data(), follow=True)
        self.assertRedirects(resp, reverse('home'))
        self.assertContains(resp, 'offboarding form sent.')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['tickets@example.edu'])
        self.assertIn('off_lab', mail.outbox[0].body)
        self.assertIn('fully offboard', mail.outbox[0].body)

    @override_settings(EMAIL_TICKET_SYSTEM_ADDRESS='tickets@example.edu', EMAIL_ENABLED=True)
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
        self.assertNotContains(resp, 'offboarding form sent.')

    def test_date_required(self):
        self.client.force_login(self.pi)
        resp = self.client.post(self.form_url(), {})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('offboarding_date', resp.context['form'].errors)
