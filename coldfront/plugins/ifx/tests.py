from unittest.mock import patch

import requests
from django.test import TestCase, override_settings

from coldfront.core.project.models import ProjectUser
from coldfront.core.test_helpers.factories import (
    ProjectFactory,
    ProjectUserFactory,
    ProjectUserStatusChoiceFactory,
    UserFactory,
)
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


NANITES_AFFILIATION_URL = 'https://nanites.example.org/affiliations'


@override_settings(
    NANITES_AFFILIATION_URL=NANITES_AFFILIATION_URL,
    IFX_MANAGER=IFX_MANAGERS,
    EMAIL_SENDER='coldfront@example.org',
)
class ProjectUserAffiliationSyncTest(TestCase):
    """Tests for reporting ProjectUser additions and removals to Nanites"""

    def setUp(self):
        self.user = UserFactory(username='sdpoisson', ifxid='IFXID0001')
        self.lab = OrganizationFactory(name='Poisson Lab', rank='lab', ifxorg='IFXORG0001')
        # Projects are created outside captureOnCommitCallbacks, so their org-linking callback never runs
        self.project = ProjectFactory(title='poisson_lab')
        ProjectOrganization.objects.create(project=self.project, organization=self.lab)
        self.active = ProjectUserStatusChoiceFactory(name='Active')
        self.removed = ProjectUserStatusChoiceFactory(name='Removed')
        self.deactivated = ProjectUserStatusChoiceFactory(name='Deactivated')

        post_patcher = patch('coldfront.plugins.ifx.affiliations.requests.post')
        self.mock_post = post_patcher.start()
        self.addCleanup(post_patcher.stop)
        self.mock_post.return_value.json.return_value = [
            {'ifxid': 'IFXID0001', 'ifxorg': 'IFXORG0001', 'message': 'affiliation updated'}
        ]
        send_patcher = patch('coldfront.plugins.ifx.models.send')
        self.mock_send = send_patcher.start()
        self.addCleanup(send_patcher.stop)

    def make_projectuser(self, status, project=None, user=None):
        """Create a ProjectUser and run the on_commit callbacks it registers"""
        with self.captureOnCommitCallbacks(execute=True):
            return ProjectUserFactory(project=project or self.project, user=user or self.user, status=status)

    def set_status(self, projectuser, status):
        with self.captureOnCommitCallbacks(execute=True):
            projectuser.status = status
            projectuser.save()

    def posted_entries(self):
        """Return the JSON body of the single Nanites POST"""
        self.mock_post.assert_called_once()
        return self.mock_post.call_args.kwargs['json']

    def test_add_sends_active_entry(self):
        self.make_projectuser(self.active)
        self.assertEqual(self.posted_entries(), [{'ifxid': 'IFXID0001', 'ifxorg': 'IFXORG0001', 'active': True}])
        self.assertEqual(self.mock_post.call_args.args[0], NANITES_AFFILIATION_URL)
        self.assertTrue(self.mock_post.call_args.kwargs['headers']['Authorization'].startswith('Token '))
        self.assertIn('timeout', self.mock_post.call_args.kwargs)

    def test_readd_after_removal_sends_active_entry(self):
        projectuser = self.make_projectuser(self.removed)
        self.mock_post.assert_not_called()
        self.set_status(projectuser, self.active)
        self.assertEqual(self.posted_entries()[0]['active'], True)

    def test_removal_sends_inactive_entry(self):
        projectuser = self.make_projectuser(self.active)
        self.mock_post.reset_mock()
        self.set_status(projectuser, self.removed)
        self.assertEqual(self.posted_entries(), [{'ifxid': 'IFXID0001', 'ifxorg': 'IFXORG0001', 'active': False}])

    def test_removal_skipped_when_other_project_shares_org(self):
        other_project = ProjectFactory(title='poisson_lab_2')
        ProjectOrganization.objects.create(project=other_project, organization=self.lab)
        self.make_projectuser(self.active, project=other_project)
        projectuser = self.make_projectuser(self.active)
        self.mock_post.reset_mock()
        self.set_status(projectuser, self.removed)
        self.mock_post.assert_not_called()

    def test_removal_sent_when_other_org_project_membership_removed(self):
        other_project = ProjectFactory(title='poisson_lab_2')
        ProjectOrganization.objects.create(project=other_project, organization=self.lab)
        self.make_projectuser(self.removed, project=other_project)
        projectuser = self.make_projectuser(self.active)
        self.mock_post.reset_mock()
        self.set_status(projectuser, self.removed)
        self.assertEqual(self.posted_entries()[0]['active'], False)

    def test_removal_checked_per_org(self):
        second_org = OrganizationFactory(name='Poisson Center', rank='center', ifxorg='IFXORG0002')
        ProjectOrganization.objects.create(project=self.project, organization=second_org)
        other_project = ProjectFactory(title='poisson_center')
        ProjectOrganization.objects.create(project=other_project, organization=second_org)
        self.make_projectuser(self.active, project=other_project)
        projectuser = self.make_projectuser(self.active)
        self.mock_post.reset_mock()
        self.set_status(projectuser, self.removed)
        self.assertEqual(self.posted_entries(), [{'ifxid': 'IFXID0001', 'ifxorg': 'IFXORG0001', 'active': False}])

    def test_one_entry_per_org(self):
        second_org = OrganizationFactory(name='Poisson Center', rank='center', ifxorg='IFXORG0002')
        ProjectOrganization.objects.create(project=self.project, organization=second_org)
        self.make_projectuser(self.active)
        self.assertCountEqual(self.posted_entries(), [
            {'ifxid': 'IFXID0001', 'ifxorg': 'IFXORG0001', 'active': True},
            {'ifxid': 'IFXID0001', 'ifxorg': 'IFXORG0002', 'active': True},
        ])

    def test_no_org_emails_ifx_managers(self):
        project = ProjectFactory(title='gordon_lab')
        self.make_projectuser(self.active, project=project)
        self.mock_post.assert_not_called()
        self.mock_send.assert_called_once()
        email = self.mock_send.call_args.kwargs
        self.assertEqual(email['to'], ','.join(IFX_MANAGERS))
        self.assertIn('Could not identify an organization for project gordon_lab', email['subject'])
        self.assertIn('User sdpoisson with ifxuser id IFXID0001 was added to the project', email['message'])

    def test_no_org_removal_email_says_removed(self):
        project = ProjectFactory(title='gordon_lab')
        projectuser = self.make_projectuser(self.active, project=project)
        self.mock_send.reset_mock()
        self.set_status(projectuser, self.removed)
        self.assertIn('was removed from the project', self.mock_send.call_args.kwargs['message'])

    def test_org_without_ifxorg_counts_as_no_org(self):
        project = ProjectFactory(title='gordon_lab')
        ProjectOrganization.objects.create(project=project, organization=OrganizationFactory(name='Gordon Lab'))
        self.make_projectuser(self.active, project=project)
        self.mock_post.assert_not_called()
        self.mock_send.assert_called_once()

    def test_deactivation_and_reactivation_not_synced(self):
        projectuser = self.make_projectuser(self.active)
        self.mock_post.reset_mock()
        self.set_status(projectuser, self.deactivated)
        self.set_status(projectuser, self.active)
        self.mock_post.assert_not_called()

    def test_unchanged_status_not_synced(self):
        projectuser = self.make_projectuser(self.active)
        self.mock_post.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            projectuser.enable_notifications = False
            projectuser.save()
        self.mock_post.assert_not_called()

    @patch('coldfront.plugins.ifx.affiliations.logger')
    def test_user_without_ifxid_skipped(self, mock_logger):
        user = UserFactory(username='noifxid', ifxid=None)
        self.make_projectuser(self.active, user=user)
        self.mock_post.assert_not_called()
        mock_logger.error.assert_called_once()

    @override_settings(NANITES_AFFILIATION_URL=None)
    def test_no_url_skips_post(self):
        self.make_projectuser(self.active)
        self.mock_post.assert_not_called()

    @patch('coldfront.plugins.ifx.affiliations.logger')
    def test_response_logged(self, mock_logger):
        self.make_projectuser(self.active)
        logged = ' '.join(str(call.args[0]) for call in mock_logger.info.call_args_list)
        self.assertIn('ifxid IFXID0001, ifxorg IFXORG0001: affiliation updated', logged)

    @patch('coldfront.plugins.ifx.affiliations.logger')
    def test_request_error_logged_not_raised(self, mock_logger):
        self.mock_post.side_effect = requests.ConnectionError('nanites down')
        projectuser = self.make_projectuser(self.active)
        self.assertTrue(projectuser.pk)
        mock_logger.error.assert_called_once()

    @patch('coldfront.plugins.ifx.affiliations.logger')
    def test_http_error_logged_not_raised(self, mock_logger):
        self.mock_post.return_value.raise_for_status.side_effect = requests.HTTPError('500')
        self.make_projectuser(self.active)
        mock_logger.error.assert_called_once()

    @patch('coldfront.plugins.ifx.affiliations.logger')
    def test_unexpected_response_logged(self, mock_logger):
        self.mock_post.return_value.json.return_value = {'detail': 'not a list'}
        self.make_projectuser(self.active)
        mock_logger.error.assert_called_once()

    def test_group_reactivation_syncs_removed_projectusers(self):
        """The other-group reactivation saves per row, so Removed -> Active is synced"""
        from coldfront.core.project.utils import reactivate_group_projectusers

        self.make_projectuser(self.removed)
        with self.captureOnCommitCallbacks(execute=True):
            reactivate_group_projectusers(self.user, {'poisson_lab'})
        self.assertEqual(self.posted_entries(), [{'ifxid': 'IFXID0001', 'ifxorg': 'IFXORG0001', 'active': True}])
