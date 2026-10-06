from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings

from coldfront.core.test_helpers.factories import ProjectFactory, UserFactory
from coldfront.core.test_helpers.fasrc_factories import OrganizationFactory, UserAffiliationFactory
from coldfront.plugins.ifx.models import ProjectOrganization, set_project_organization


class SetProjectOrganizationTest(TestCase):
    """Tests for matching a Project to the Harvard lab Organization its PI leads"""

    def setUp(self):
        self.pi = UserFactory(username='sdpoisson')
        self.lab = OrganizationFactory(name='Poisson Lab', rank='lab', org_tree='Harvard')

    def make_project(self, title='poisson_lab'):
        """Create a Project without running the post_save on_commit callback"""
        return ProjectFactory(title=title, pi=self.pi)

    def affiliate(self, organization, role='pi'):
        return UserAffiliationFactory(user=self.pi, organization=organization, role=role)

    def test_links_pi_lab_matching_project_title(self):
        self.affiliate(self.lab)
        project = self.make_project()
        project_organization, message = set_project_organization(project)
        self.assertEqual(project_organization.organization, self.lab)
        self.assertIn('Linked project "poisson_lab" to organization "Poisson Lab"', message)
        self.assertTrue(ProjectOrganization.objects.filter(project=project, organization=self.lab).exists())

    def test_title_match_ignores_case(self):
        self.affiliate(self.lab)
        project = self.make_project(title='POISSON_LAB')
        project_organization, _ = set_project_organization(project)
        self.assertIsNotNone(project_organization)

    def test_no_link_when_title_lacks_org_first_word(self):
        self.affiliate(self.lab)
        project = self.make_project(title='gordon_lab')
        project_organization, message = set_project_organization(project)
        self.assertIsNone(project_organization)
        self.assertIn('does not contain first word of organization name "Poisson Lab"', message)
        self.assertFalse(ProjectOrganization.objects.filter(project=project).exists())

    def test_no_link_without_pi_affiliation(self):
        project = self.make_project()
        project_organization, message = set_project_organization(project)
        self.assertIsNone(project_organization)
        self.assertIn('is not a PI for any Harvard lab Organization', message)
        self.assertFalse(ProjectOrganization.objects.filter(project=project).exists())

    def test_no_link_when_affiliation_role_is_not_pi(self):
        self.affiliate(self.lab, role='user')
        project = self.make_project()
        project_organization, _ = set_project_organization(project)
        self.assertIsNone(project_organization)

    def test_no_link_when_organization_is_not_a_lab(self):
        department = OrganizationFactory(name='Poisson Department', rank='department', org_tree='Harvard')
        self.affiliate(department)
        project = self.make_project()
        project_organization, _ = set_project_organization(project)
        self.assertIsNone(project_organization)

    def test_no_link_when_organization_is_not_in_harvard_tree(self):
        other_lab = OrganizationFactory(name='Poisson Group', rank='lab', org_tree='Research Computing')
        self.affiliate(other_lab)
        project = self.make_project()
        project_organization, _ = set_project_organization(project)
        self.assertIsNone(project_organization)

    def test_no_link_when_pi_leads_multiple_labs(self):
        self.affiliate(self.lab)
        self.affiliate(OrganizationFactory(name='Poisson Other Lab', rank='lab', org_tree='Harvard'))
        project = self.make_project()
        project_organization, message = set_project_organization(project)
        self.assertIsNone(project_organization)
        self.assertIn('is a multiple', message)
        self.assertFalse(ProjectOrganization.objects.filter(project=project).exists())


IFX_MANAGERS = ['manager1@example.org', 'manager2@example.org']


@patch('coldfront.core.utils.mail.EMAIL_ENABLED', True)
@override_settings(IFX_MANAGER=IFX_MANAGERS, EMAIL_SENDER='coldfront@example.org')
class ProjectPostSaveTest(TestCase):
    """Tests for the Project post_save receiver that calls set_project_organization"""

    def setUp(self):
        self.pi = UserFactory(username='sdpoisson')
        lab = OrganizationFactory(name='Poisson Lab', rank='lab', org_tree='Harvard')
        UserAffiliationFactory(user=self.pi, organization=lab, role='pi')

    def create_project(self, title='poisson_lab'):
        """Create a Project and run the on_commit callback its post_save registers"""
        with self.captureOnCommitCallbacks(execute=True):
            return ProjectFactory(title=title, pi=self.pi)

    def test_project_organization_created_on_project_creation(self):
        project = self.create_project()
        self.assertTrue(ProjectOrganization.objects.filter(project=project).exists())

    def test_success_emailed_to_ifx_managers(self):
        self.create_project()
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, IFX_MANAGERS)
        self.assertIn('Project poisson_lab linked to organization Poisson Lab', sent.subject)
        self.assertIn('Linked project "poisson_lab" to organization "Poisson Lab"', sent.body)

    def test_unlinked_result_emailed_to_ifx_managers(self):
        self.create_project(title='gordon_lab')
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, IFX_MANAGERS)
        self.assertIn('Project gordon_lab not linked to an organization', sent.subject)
        self.assertIn('does not contain first word of organization name', sent.body)

    @patch('coldfront.plugins.ifx.models.logger')
    @patch('coldfront.plugins.ifx.models.set_project_organization', side_effect=Exception('lookup failed'))
    def test_error_does_not_block_project_creation(self, mock_set_project_organization, mock_logger):
        project = self.create_project()
        mock_logger.error.assert_called_once()
        self.assertTrue(project.pk)
        mock_set_project_organization.assert_called_once()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('not linked to an organization', mail.outbox[0].subject)
        self.assertIn('lookup failed', mail.outbox[0].body)

    @override_settings(IFX_MANAGER=[])
    def test_no_email_without_ifx_managers(self):
        project = self.create_project()
        self.assertTrue(ProjectOrganization.objects.filter(project=project).exists())
        self.assertEqual(len(mail.outbox), 0)

    @patch('coldfront.plugins.ifx.models.logger')
    @patch('coldfront.plugins.ifx.models.send_email', side_effect=Exception('smtp down'))
    def test_email_error_does_not_block_project_creation(self, mock_send_email, mock_logger):
        project = self.create_project()
        mock_logger.error.assert_called_once()
        self.assertTrue(ProjectOrganization.objects.filter(project=project).exists())
        mock_send_email.assert_called_once()

    @patch('coldfront.plugins.ifx.models.set_project_organization', return_value=(None, ''))
    def test_not_called_on_project_update(self, mock_set_project_organization):
        project = self.create_project()
        mock_set_project_organization.reset_mock()
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            project.description = 'updated'
            project.save()
        mock_set_project_organization.assert_not_called()
        self.assertEqual(len(mail.outbox), 0)
