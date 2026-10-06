from unittest.mock import patch

from django.test import TestCase

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
        project_organization = set_project_organization(project)
        self.assertEqual(project_organization.organization, self.lab)
        self.assertTrue(ProjectOrganization.objects.filter(project=project, organization=self.lab).exists())

    def test_title_match_ignores_case(self):
        self.affiliate(self.lab)
        project = self.make_project(title='POISSON_LAB')
        self.assertIsNotNone(set_project_organization(project))

    def test_no_link_when_title_lacks_org_first_word(self):
        self.affiliate(self.lab)
        project = self.make_project(title='gordon_lab')
        self.assertIsNone(set_project_organization(project))
        self.assertFalse(ProjectOrganization.objects.filter(project=project).exists())

    def test_no_link_without_pi_affiliation(self):
        project = self.make_project()
        self.assertIsNone(set_project_organization(project))
        self.assertFalse(ProjectOrganization.objects.filter(project=project).exists())

    def test_no_link_when_affiliation_role_is_not_pi(self):
        self.affiliate(self.lab, role='user')
        project = self.make_project()
        self.assertIsNone(set_project_organization(project))

    def test_no_link_when_organization_is_not_a_lab(self):
        department = OrganizationFactory(name='Poisson Department', rank='department', org_tree='Harvard')
        self.affiliate(department)
        project = self.make_project()
        self.assertIsNone(set_project_organization(project))

    def test_no_link_when_organization_is_not_in_harvard_tree(self):
        other_lab = OrganizationFactory(name='Poisson Group', rank='lab', org_tree='Research Computing')
        self.affiliate(other_lab)
        project = self.make_project()
        self.assertIsNone(set_project_organization(project))

    def test_no_link_when_pi_leads_multiple_labs(self):
        self.affiliate(self.lab)
        self.affiliate(OrganizationFactory(name='Poisson Other Lab', rank='lab', org_tree='Harvard'))
        project = self.make_project()
        self.assertIsNone(set_project_organization(project))
        self.assertFalse(ProjectOrganization.objects.filter(project=project).exists())


class ProjectPostSaveTest(TestCase):
    """Tests for the Project post_save receiver that calls set_project_organization"""

    def setUp(self):
        self.pi = UserFactory(username='sdpoisson')
        lab = OrganizationFactory(name='Poisson Lab', rank='lab', org_tree='Harvard')
        UserAffiliationFactory(user=self.pi, organization=lab, role='pi')

    def test_project_organization_created_on_project_creation(self):
        with self.captureOnCommitCallbacks(execute=True):
            project = ProjectFactory(title='poisson_lab', pi=self.pi)
        self.assertTrue(ProjectOrganization.objects.filter(project=project).exists())

    @patch('coldfront.plugins.ifx.models.set_project_organization')
    def test_not_called_on_project_update(self, mock_set_project_organization):
        with self.captureOnCommitCallbacks(execute=True):
            project = ProjectFactory(title='poisson_lab', pi=self.pi)
        mock_set_project_organization.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            project.description = 'updated'
            project.save()
        mock_set_project_organization.assert_not_called()

    @patch('coldfront.plugins.ifx.models.set_project_organization', side_effect=Exception('lookup failed'))
    def test_error_does_not_block_project_creation(self, mock_set_project_organization):
        with self.captureOnCommitCallbacks(execute=True):
            project = ProjectFactory(title='poisson_lab', pi=self.pi)
        self.assertTrue(project.pk)
        mock_set_project_organization.assert_called_once()
