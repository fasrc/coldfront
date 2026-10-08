from unittest.mock import patch

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

    def test_matches_word_before_lab_suffix(self):
        lab = OrganizationFactory(name='Simeon Denis Poisson Lab', rank='lab', org_tree='Harvard')
        self.affiliate(lab)
        project = self.make_project(title='poisson_lab')
        project_organization, _ = set_project_organization(project)
        self.assertEqual(project_organization.organization, lab)

    def test_matches_last_word_without_lab_suffix(self):
        group = OrganizationFactory(name='Simeon Denis Poisson', rank='lab', org_tree='Harvard')
        self.affiliate(group)
        project = self.make_project(title='poisson_lab')
        project_organization, _ = set_project_organization(project)
        self.assertEqual(project_organization.organization, group)

    def test_no_link_when_title_lacks_word_before_lab_suffix(self):
        lab = OrganizationFactory(name='Poisson Gordon Lab', rank='lab', org_tree='Harvard')
        self.affiliate(lab)
        project = self.make_project(title='poisson_lab')
        project_organization, _ = set_project_organization(project)
        self.assertIsNone(project_organization)

    def test_no_link_when_title_fails_string_check(self):
        self.affiliate(self.lab)
        project = self.make_project(title='gordon_lab')
        project_organization, message = set_project_organization(project)
        self.assertIsNone(project_organization)
        self.assertIn('failed string check for organization name "Poisson Lab"', message)
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


@override_settings(IFX_MANAGER=IFX_MANAGERS, EMAIL_SENDER='coldfront@example.org')
class ProjectPostSaveTest(TestCase):
    """Tests for the Project post_save receiver that calls set_project_organization"""

    def setUp(self):
        self.pi = UserFactory(username='sdpoisson')
        lab = OrganizationFactory(name='Poisson Lab', rank='lab', org_tree='Harvard')
        UserAffiliationFactory(user=self.pi, organization=lab, role='pi')
        # ifxmail sends through the IfxMail API
        send_patcher = patch('coldfront.plugins.ifx.models.send')
        self.mock_send = send_patcher.start()
        self.addCleanup(send_patcher.stop)

    def create_project(self, title='poisson_lab'):
        """Create a Project and run the on_commit callback its post_save registers"""
        with self.captureOnCommitCallbacks(execute=True):
            return ProjectFactory(title=title, pi=self.pi)

    def sent_email(self):
        """Return the kwargs of the single ifxmail send call"""
        self.mock_send.assert_called_once()
        return self.mock_send.call_args.kwargs

    def test_project_organization_created_on_project_creation(self):
        project = self.create_project()
        self.assertTrue(ProjectOrganization.objects.filter(project=project).exists())

    def test_success_emailed_to_ifx_managers(self):
        self.create_project()
        email = self.sent_email()
        self.assertEqual(email['to'], ','.join(IFX_MANAGERS))
        self.assertEqual(email['fromaddr'], 'coldfront@example.org')
        self.assertIn('Project poisson_lab linked to organization Poisson Lab', email['subject'])
        self.assertIn('Linked project "poisson_lab" to organization "Poisson Lab"', email['message'])

    def test_unlinked_result_emailed_to_ifx_managers(self):
        self.create_project(title='gordon_lab')
        email = self.sent_email()
        self.assertEqual(email['to'], ','.join(IFX_MANAGERS))
        self.assertIn('Project gordon_lab not linked to an organization', email['subject'])
        self.assertIn('failed string check', email['message'])

    @patch('coldfront.plugins.ifx.models.logger')
    @patch('coldfront.plugins.ifx.models.set_project_organization', side_effect=Exception('lookup failed'))
    def test_error_does_not_block_project_creation(self, mock_set_project_organization, mock_logger):
        project = self.create_project()
        self.assertTrue(project.pk)
        mock_logger.error.assert_called_once()
        email = self.sent_email()
        self.assertIn('not linked to an organization', email['subject'])
        self.assertIn('lookup failed', email['message'])

    @patch('coldfront.plugins.ifx.models.logger')
    @override_settings(IFX_MANAGER=[])
    def test_no_email_without_ifx_managers(self, mock_logger):
        project = self.create_project()
        self.assertTrue(ProjectOrganization.objects.filter(project=project).exists())
        self.mock_send.assert_not_called()
        mock_logger.error.assert_called_once()

    @patch('coldfront.plugins.ifx.models.logger')
    def test_email_error_does_not_block_project_creation(self, mock_logger):
        self.mock_send.side_effect = Exception('ifxmail down')
        project = self.create_project()
        self.assertTrue(ProjectOrganization.objects.filter(project=project).exists())
        mock_logger.exception.assert_called_once()

    @patch('coldfront.plugins.ifx.models.set_project_organization', return_value=(None, ''))
    def test_not_called_on_project_update(self, mock_set_project_organization):
        project = self.create_project()
        mock_set_project_organization.reset_mock()
        self.mock_send.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            project.description = 'updated'
            project.save()
        mock_set_project_organization.assert_not_called()
        self.mock_send.assert_not_called()
