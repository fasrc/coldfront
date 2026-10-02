from unittest.mock import patch, MagicMock

from django.test import TestCase

from coldfront.core.test_helpers.factories import ProjectFactory
from coldfront.core.test_helpers.fasrc_factories import OrganizationFactory
from coldfront.plugins.ifx.models import ProjectOrganization

UTIL_PATH = 'coldfront.plugins.ifx.models'


def rc_sister(rc, harvard):
    """Mock a Nanites RC / Harvard sister mapping"""
    sister = MagicMock()
    sister.rc = rc
    sister.harvard = harvard
    return sister


@patch(f'{UTIL_PATH}.NanitesAPI')
class ProjectPostSaveTest(TestCase):
    """Tests for creating ProjectOrganizations when a Project is created"""

    def setUp(self):
        self.organization = OrganizationFactory(name='Poisson Lab', ifxorg='IFXORG0001')

    def create_project(self, **kwargs):
        """Create a Project and run the on_commit callbacks its post_save registers"""
        with self.captureOnCommitCallbacks(execute=True):
            return ProjectFactory(**kwargs)

    def test_project_organization_created_when_sister_exists(self, mock_nanites):
        mock_nanites.getRcSisters.return_value = [
            rc_sister('other_lab', 'IFXORG9999'),
            rc_sister('poisson_lab', 'IFXORG0001'),
        ]
        project = self.create_project(title='poisson_lab')
        self.assertTrue(
            ProjectOrganization.objects.filter(project=project, organization=self.organization).exists()
        )

    def test_no_project_organization_without_sister(self, mock_nanites):
        mock_nanites.getRcSisters.return_value = [rc_sister('other_lab', 'IFXORG0001')]
        project = self.create_project(title='poisson_lab')
        self.assertFalse(ProjectOrganization.objects.filter(project=project).exists())

    def test_no_project_organization_without_organization(self, mock_nanites):
        mock_nanites.getRcSisters.return_value = [rc_sister('poisson_lab', 'IFXORG9999')]
        project = self.create_project(title='poisson_lab')
        self.assertFalse(ProjectOrganization.objects.filter(project=project).exists())

    def test_nanites_error_does_not_block_project_creation(self, mock_nanites):
        mock_nanites.getRcSisters.side_effect = Exception('nanites unavailable')
        project = self.create_project(title='poisson_lab')
        self.assertTrue(project.pk)
        self.assertFalse(ProjectOrganization.objects.filter(project=project).exists())

    def test_not_called_on_project_update(self, mock_nanites):
        mock_nanites.getRcSisters.return_value = []
        project = self.create_project(title='poisson_lab')
        mock_nanites.getRcSisters.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            project.description = 'updated'
            project.save()
        mock_nanites.getRcSisters.assert_not_called()
