import datetime
import logging

from bs4 import BeautifulSoup

from django.contrib.auth.models import Group
from django.core import mail
from django.utils import timezone
from django.test import TestCase, override_settings
from django.urls import reverse
from unittest.mock import call, patch

from coldfront.core.test_helpers import utils
from coldfront.core.utils.common import import_from_settings
from coldfront.core.test_helpers.factories import (
    setup_models,
    ProjectFactory,
    ProjectUserFactory,
    PAttributeTypeFactory,
    ProjectAttributeFactory,
    ProjectStatusChoiceFactory,
    ProjectAttributeTypeFactory,
    ResourceAttributeFactory,
    UserFactory,
)
from coldfront.core.allocation.models import AllocationUserStatusChoice
from coldfront.core.project.views import ProjectAddUsersView, ProjectRemoveUsersView
from coldfront.core.resource.models import ResourceAttributeType
from coldfront.core.project.models import (
    Project, ProjectUser,
    ProjectUserRoleChoice,
    ProjectUserStatusChoice
)

logging.disable(logging.CRITICAL)

EXTERNAL_USER_GROUPS = import_from_settings('EXTERNAL_USER_GROUPS', ['external', 'vendor'])
EXTERNAL_EXPIRATION_MAX_DAYS = import_from_settings('EXTERNAL_EXPIRATION_MAX_DAYS', 90)
VENDOR_USER_GROUP = import_from_settings('VENDOR_USER_GROUP', 'vendor')
VENDOR_EXPIRATION_MAX_DAYS = import_from_settings('VENDOR_EXPIRATION_MAX_DAYS', 30)

UTIL_FIXTURES = [
        "coldfront/core/test_helpers/test_data/test_fixtures/ifx.json",
]

class ProjectViewTestBase(TestCase):
    """Base class for project view tests"""
    fixtures = UTIL_FIXTURES

    @classmethod
    def setUpTestData(cls):
        """Set up users and project for testing"""
        setup_models(cls)
        cls.project_user = cls.proj_allocationuser
        cls.nonproject_user = cls.nonproj_allocationuser
        # add pi_user and project_user to project_user

        attributetype = PAttributeTypeFactory(name='string')
        cls.projectattributetype = ProjectAttributeTypeFactory(attribute_type=attributetype)# ProjectAttributeType.objects.get(pk=1)

    def project_access_tstbase(self, url):
        """Test basic access control for project views. For all project views:
        - if not logged in, redirect to login page
        - if logged in as admin, can access page
        """
        # If not logged in, can't see page; redirect to login page.
        utils.test_logged_out_redirect_to_login(self, url)
        # after login, pi and admin can access create page
        utils.test_user_can_access(self, self.admin_user, url)


class ArchivedProjectViewsTest(ProjectViewTestBase):
    """tests for Views of an archived project"""

    @classmethod
    def setUpTestData(cls):
        """Set up users and project for testing"""
        super(ArchivedProjectViewsTest, cls).setUpTestData()
        cls.project.status = ProjectStatusChoiceFactory(name='Archived')
        cls.project.save()

    def test_projectdetail_warning_visible(self):
        """Test that warning is visible on archived project detail page"""
        url = f'/project/{self.project.pk}/'
        utils.page_contains_for_user(self, self.pi_user, url, 'You cannot make any changes')

    def test_projectlist_no_archived_projects(self):
        """Test that archived projects are not visible on project list page"""
        url = '/project/?show_all_projects=True&'
        response = utils.login_and_get_page(self.client, self.pi_user, url)
        self.assertNotContains(response, self.project.title)

    def test_archived_projectlist(self):
        """Test that archived projects are visible on archived project list page"""
        url = '/project/archived/'#?show_all_projects=True&'
        utils.page_contains_for_user(self, self.pi_user, url, self.project.title)


class ProjectArchiveProjectViewTest(ProjectViewTestBase):
    """Tests for project archive project view"""

    @classmethod
    def setUpTestData(cls):
        """Set up users and project for testing"""
        super(ProjectArchiveProjectViewTest, cls).setUpTestData()
        cls.url = f'/project/{cls.project.pk}/archive'

    def test_project_archive_project_access(self):
        """Test access to project archive project page"""
        # logged-out user gets redirected, admin can access archive project page
        self.project_access_tstbase(self.url)
        # pi, projectuser and nonproject user cannot access archive project page
        utils.test_user_cannot_access(self, self.pi_user, self.url)
        utils.test_user_cannot_access(self, self.project_user, self.url)
        utils.test_user_cannot_access(self, self.nonproject_user, self.url)

    def test_project_archive_project_post(self):
        """Test project archive project post response"""
        self.client.force_login(self.admin_user,
                    backend='django.contrib.auth.backends.ModelBackend')
        response = self.client.post(self.url)
        self.assertRedirects(
            response, f'/project/{self.project.pk}/', status_code=302, target_status_code=200)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status.name, 'Archived')


class ProjectUnArchiveProjectViewTest(ProjectViewTestBase):
    """Tests for project unarchive project view"""

    @classmethod
    def setUpTestData(cls):
        """Set up users and project for testing"""
        super(ProjectUnArchiveProjectViewTest, cls).setUpTestData()
        cls.project.status = ProjectStatusChoiceFactory(name='Archived')
        cls.project.save()
        cls.url = f'/project/{cls.project.pk}/unarchive'

    def test_project_unarchive_project_access(self):
        """Test access to project unarchive project page"""
        # logged-out user gets redirected, admin can access unarchive project page
        self.project_access_tstbase(self.url)
        # pi, projectuser and nonproject user cannot access unarchive project page
        utils.test_user_cannot_access(self, self.pi_user, self.url)
        utils.test_user_cannot_access(self, self.project_user, self.url)
        utils.test_user_cannot_access(self, self.nonproject_user, self.url)

    def test_project_unarchive_project_post(self):
        """Test project unarchive project post response"""
        self.client.force_login(self.admin_user,
                    backend='django.contrib.auth.backends.ModelBackend')
        response = self.client.post(self.url)
        self.assertRedirects(
            response, f'/project/{self.project.pk}/', status_code=302, target_status_code=200)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status.name, 'Active')


class ProjectCreateTest(ProjectViewTestBase):
    """Tests for project create view"""

    @classmethod
    def setUpTestData(cls):
        """Set up users and project for testing"""
        super(ProjectCreateTest, cls).setUpTestData()
        cls.url = '/project/create/'

    def test_project_access(self):
        """Test access to project create page"""
        # logged-out user gets redirected, admin can access create page
        self.project_access_tstbase(self.url)
        # pi, projectuser and nonproject user cannot access create page
        utils.test_user_cannot_access(self, self.pi_user, self.url)
        utils.test_user_cannot_access(self, self.project_user, self.url)
        utils.test_user_cannot_access(self, self.nonproject_user, self.url)


class ProjectAttributeCreateTest(ProjectViewTestBase):
    """Tests for project attribute create view"""

    @classmethod
    def setUpTestData(cls):
        """Set up users and project for testing"""
        super(ProjectAttributeCreateTest, cls).setUpTestData()
        int_attributetype = PAttributeTypeFactory(name='Int')
        cls.int_projectattributetype = ProjectAttributeTypeFactory(attribute_type=int_attributetype)
        cls.url = f'/project/{cls.project.pk}/project-attribute-create/'

    def test_project_access(self):
        """Test access to project attribute create page"""
        # logged-out user gets redirected, admin can access create page
        self.project_access_tstbase(self.url)
        # pi, project user and nonproject user cannot access create page
        utils.test_user_cannot_access(self, self.pi_user, self.url)
        utils.test_user_cannot_access(self, self.project_user, self.url)
        utils.test_user_cannot_access(self, self.nonproject_user, self.url)

    def test_project_attribute_create_post(self):
        """Test project attribute creation post response"""

        self.client.force_login(self.admin_user,
                    backend='django.contrib.auth.backends.ModelBackend')
        response = self.client.post(self.url, data={
                                'proj_attr_type': self.projectattributetype.pk,
                                'value': 'test_value',
                                'project': self.project.pk
                                })
        self.assertRedirects(response, f'/project/{self.project.pk}/', status_code=302, target_status_code=200)

    def test_project_attribute_create_post_required_values(self):
        """ProjectAttributeCreate correctly flags missing project or value
        """
        self.client.force_login(self.admin_user,
                    backend='django.contrib.auth.backends.ModelBackend')
        # missing project
        response = self.client.post(self.url, data={
            'proj_attr_type': self.projectattributetype.pk, 'value': 'test_value'
        })
        self.assertFormError(response, 'form', 'project', 'This field is required.')
        # missing value
        response = self.client.post(self.url, data={
            'proj_attr_type': self.projectattributetype.pk, 'project': self.project.pk
        })
        self.assertFormError(response, 'form', 'value', 'This field is required.')

    def test_project_attribute_create_value_type_match(self):
        """ProjectAttributeCreate correctly flags value-type mismatch"""
        self.client.force_login(self.admin_user,
                    backend='django.contrib.auth.backends.ModelBackend')
        # test that value must be numeric if proj_attr_type is string
        response = self.client.post(self.url, data={
            'proj_attr_type': self.int_projectattributetype.pk,
            'value': True,
            'project': self.project.pk
        })
        self.assertContains(response, 'Invalid Value True. Value must be an int.')


class ProjectAttributeUpdateTest(ProjectViewTestBase):

    @classmethod
    def setUpTestData(cls):
        """Set up users and project for testing"""
        super(ProjectAttributeUpdateTest, cls).setUpTestData()
        cls.projectattribute = ProjectAttributeFactory(
            value=36238, proj_attr_type=cls.projectattributetype, project=cls.project
        )
        cls.url = f'/project/{cls.project.pk}/project-attribute-update/{cls.projectattribute.pk}'

    def test_project_attribute_update_access(self):
        """Test access to project attribute update page"""
        self.project_access_tstbase(self.url)
        # project user, pi, and nonproject user cannot access update page
        utils.test_user_cannot_access(self, self.pi_user, self.url)
        utils.test_user_cannot_access(self, self.project_user, self.url)
        utils.test_user_cannot_access(self, self.nonproject_user, self.url)


class ProjectAttributeDeleteTest(ProjectViewTestBase):
    """Tests for ProjectAttributeDeleteView"""

    @classmethod
    def setUpTestData(cls):
        """set up users and project for testing"""
        super(ProjectAttributeDeleteTest, cls).setUpTestData()
        cls.projectattribute = ProjectAttributeFactory(value=36238, proj_attr_type=cls.projectattributetype, project=cls.project)
        cls.url = f'/project/{cls.project.pk}/project-attribute-delete/'

    def test_project_attribute_delete_access(self):
        """test access to project attribute delete page"""
        # logged-out user gets redirected, admin can access delete page
        self.project_access_tstbase(self.url)
        # pi, project user and nonproject user cannot access delete page
        utils.test_user_cannot_access(self, self.pi_user, self.url)
        utils.test_user_cannot_access(self, self.project_user, self.url)
        utils.test_user_cannot_access(self, self.nonproject_user, self.url)


class ProjectListViewTest(ProjectViewTestBase):
    """Tests for projectlist view"""

    @classmethod
    def setUpTestData(cls):
        """Set up users and project for testing"""
        super(ProjectListViewTest, cls).setUpTestData()
        # add 100 projects to test pagination, permissions, search functionality
        cls.additional_projects = [ProjectFactory() for i in list(range(100))]
        cls.url = '/project/'

    ### ProjectListView access tests ###

    def test_project_list_access(self):
        """Test project list access controls."""
        # logged-out user gets redirected, admin can access list page
        self.project_access_tstbase(self.url)
        # all other users can access list page
        utils.test_user_can_access(self, self.pi_user, self.url)
        utils.test_user_can_access(self, self.project_user, self.url)
        utils.test_user_can_access(self, self.nonproject_user, self.url)

    ### ProjectListView display tests ###

    def test_project_list_display_members(self):
        """Test that project list displays only projects that user is an active member of."""
        # deactivated projectuser won't see project on their page
        self.npu.status, _ = ProjectUserStatusChoice.objects.get_or_create(name='Removed')
        self.npu.save()
        response = utils.login_and_get_page(self.client, self.normal_projuser, self.url)
        self.assertEqual(len(response.context['object_list']), 0)

    def test_project_list_displayall_permission_admin(self):
        """Test that the projectlist displayall option displays all projects to admin"""
        url = self.url + '?show_all_projects=on'
        response = utils.login_and_get_page(self.client, self.admin_user, url)
        self.assertEqual(len(response.context['object_list']), Project.objects.all().count())

    def test_project_list_displayall_permission_pi(self):
        """Test that the projectlist displayall option displays only the pi's projects to the pi"""
        url = self.url + '?show_all_projects=on'
        response = utils.login_and_get_page(self.client, self.pi_user, url)
        self.assertEqual(len(response.context['object_list']), 1)

    def test_project_list_displayall_permission_project_user(self):
        """Test that the projectlist displayall option displays only the project user's projects to the project user"""
        url = self.url + '?show_all_projects=on'
        response = utils.login_and_get_page(self.client, self.project_user, url)
        self.assertEqual(len(response.context['object_list']), 1)

    ### ProjectListView search tests ###

    def test_project_list_search(self):
        """Test that project list search works."""
        url_base = self.url + '?show_all_projects=on'
        # search by project project_title
        url = url_base + '&title=' + self.project.title
        response = utils.login_and_get_page(self.client, self.admin_user, url)
        self.assertEqual(len(response.context['object_list']), 1)

    def test_project_list_search_pagination(self):
        """confirm that navigation to next page of search works as expected"""
        url = self.url + '?show_all_projects=on'
        response = utils.login_and_get_page(self.client, self.admin_user, url)


class ProjectRemoveUsersViewTest(ProjectViewTestBase):
    """Tests for ProjectRemoveUsersView"""

    def setUp(self):
        """Set up users and project for testing"""
        super().setUp()
        self.url = reverse('project-remove-users', kwargs={'pk': self.project.pk})
        self.project_user = self.proj_allocationuser
        self.nonproject_user = self.nonproj_allocationuser

    @patch('coldfront.core.project.views.project_filter_users_to_remove.send', return_value=[])
    def test_projectremoveusersview_access(self, mock_filter_users_to_remove):
        """test access to project remove users page"""
        self.project_access_tstbase(self.url)

    @patch('coldfront.core.project.views.project_filter_users_to_remove.send')
    def test_pi_user_cannot_be_removed(self, mock_filter_users_to_remove):
        """Test that the project PI cannot be removed"""
        # pass the view's candidate list through unchanged, as the LDAP receiver would
        mock_filter_users_to_remove.side_effect = lambda sender, users_to_remove, project: [
            (None, users_to_remove)
        ]
        self.client.force_login(self.pi_user)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        context = response.context

        users_to_remove = context['formset'].initial
        self.assertNotIn(self.pi_user.username, [u['username'] for u in users_to_remove])

    @patch('coldfront.core.project.views.project_filter_users_to_remove.send')
    def test_is_external_column_flags_external_users(self, mock_filter_users_to_remove):
        """The Is External column follows Is Primary and is checked only for external users"""
        mock_filter_users_to_remove.side_effect = lambda sender, users_to_remove, project: [
            (None, users_to_remove)
        ]
        self.project_user.groups.add(Group.objects.get_or_create(name=EXTERNAL_USER_GROUPS[0])[0])
        self.client.force_login(self.pi_user)
        response = self.client.get(self.url)

        users = {u['username']: u for u in response.context['formset'].initial}
        self.assertTrue(users[self.project_user.username]['is_external'])
        self.assertTrue(any(not u['is_external'] for u in users.values()))

        soup = BeautifulSoup(response.content, 'html.parser')
        headers = [th.get_text(strip=True) for th in soup.find('thead').find_all('th')]
        self.assertEqual(headers.index('Is External'), headers.index('Is Primary') + 1)
        external_col = headers.index('Is External')
        for row in soup.find('tbody').find_all('tr'):
            cells = row.find_all('td')
            username = cells[headers.index('Username')].get_text(strip=True)
            has_check = cells[external_col].find('i', class_='fa-check') is not None
            self.assertEqual(has_check, users[username]['is_external'], username)

    @patch('coldfront.core.project.views.project_filter_users_to_remove.send')
    def test_primary_group_checkbox_visible_to_pi_and_general_manager(
        self, mock_filter_users_to_remove
    ):
        primary_user = self.project_user
        mock_filter_users_to_remove.return_value = [(
            None,
            [{
                'username': primary_user.username,
                'first_name': primary_user.first_name,
                'last_name': primary_user.last_name,
                'email': primary_user.email,
                'role': 'User',
                'primary_group': True,
            }]
        )]

        self.client.force_login(self.pi_user)
        response = self.client.get(self.url)
        self.assertContains(response, 'name="userform-0-selected"')

        self.client.force_login(self.proj_generalmanager)
        response = self.client.get(self.url)
        self.assertContains(response, 'name="userform-0-selected"')

    @patch('coldfront.core.project.views.project_preremove_projectuser.send')
    @patch('coldfront.core.project.views.project_filter_users_to_remove.send')
    def test_primary_group_removal_permissions(
        self, mock_filter_users_to_remove, mock_project_preremove
    ):
        primary_user = self.project_user
        project_user_obj = self.project.projectuser_set.get(user=primary_user)
        project_user_obj.status = ProjectUserStatusChoice.objects.get(name='Active')
        project_user_obj.save()

        mock_filter_users_to_remove.return_value = [(
            None,
            [{
                'username': primary_user.username,
                'first_name': primary_user.first_name,
                'last_name': primary_user.last_name,
                'email': primary_user.email,
                'role': 'User',
                'primary_group': True,
            }]
        )]
        mock_project_preremove.return_value = None

        post_data = {
            'userform-TOTAL_FORMS': '1',
            'userform-INITIAL_FORMS': '1',
            'userform-MIN_NUM_FORMS': '0',
            'userform-MAX_NUM_FORMS': '1',
            'userform-0-selected': 'on',
            'userform-0-username': primary_user.username,
            'userform-0-first_name': primary_user.first_name,
            'userform-0-last_name': primary_user.last_name,
            'userform-0-email': primary_user.email,
            'userform-0-role': 'User',
            'userform-0-primary_group': 'on',
        }

        self.client.force_login(self.proj_accessmanager)
        self.client.post(self.url, data=post_data, follow=True)
        project_user_obj.refresh_from_db()
        self.assertEqual(project_user_obj.status.name, 'Deactivated')

        self.client.force_login(self.proj_generalmanager)
        self.client.post(self.url, data=post_data, follow=True)
        project_user_obj.refresh_from_db()
        self.assertEqual(project_user_obj.status.name, 'Deactivated')

    @patch('coldfront.core.project.views.project_preremove_projectuser.send')
    @patch('coldfront.core.project.views.project_filter_users_to_remove.send')
    def test_primary_group_removal_deactivates_secondary_projects_not_removes(
        self, mock_filter_users_to_remove, mock_project_preremove
    ):
        """Deactivating a user's primary AD group disables their whole AD account,
        but doesn't remove them from their other AD groups - so their membership
        in other active projects should become Deactivated, not Removed."""
        primary_user = self.project_user
        project_user_obj = self.project.projectuser_set.get(user=primary_user)
        project_user_obj.status = ProjectUserStatusChoice.objects.get(name='Active')
        project_user_obj.save()

        other_project = ProjectFactory(
            title='other_lab', status=ProjectStatusChoiceFactory(name='Active')
        )
        other_projectuser = ProjectUserFactory(
            project=other_project, user=primary_user,
            status=ProjectUserStatusChoice.objects.get(name='Active'),
        )

        mock_filter_users_to_remove.return_value = [(
            None,
            [{
                'username': primary_user.username,
                'first_name': primary_user.first_name,
                'last_name': primary_user.last_name,
                'email': primary_user.email,
                'role': 'User',
                'primary_group': True,
            }]
        )]
        mock_project_preremove.return_value = None

        post_data = {
            'userform-TOTAL_FORMS': '1',
            'userform-INITIAL_FORMS': '1',
            'userform-MIN_NUM_FORMS': '0',
            'userform-MAX_NUM_FORMS': '1',
            'userform-0-selected': 'on',
            'userform-0-username': primary_user.username,
            'userform-0-first_name': primary_user.first_name,
            'userform-0-last_name': primary_user.last_name,
            'userform-0-email': primary_user.email,
            'userform-0-role': 'User',
            'userform-0-primary_group': 'on',
        }

        self.client.force_login(self.proj_generalmanager)
        self.client.post(self.url, data=post_data, follow=True)

        other_projectuser.refresh_from_db()
        self.assertEqual(other_projectuser.status.name, 'Deactivated')

    def _post_cluster_user_removal(self, mock_filter_users_to_remove, primary_group=False):
        """Remove proj_allocationuser from the project: as the PI, or as a General Manager
        deactivating them when the project is their primary group"""
        user = self.project_user
        mock_filter_users_to_remove.return_value = [(
            None,
            [{
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'email': user.email,
                'role': 'User',
                'primary_group': primary_group,
            }]
        )]
        post_data = {
            'userform-TOTAL_FORMS': '1',
            'userform-INITIAL_FORMS': '1',
            'userform-MIN_NUM_FORMS': '0',
            'userform-MAX_NUM_FORMS': '1',
            'userform-0-selected': 'on',
            'userform-0-username': user.username,
            'userform-0-first_name': user.first_name,
            'userform-0-last_name': user.last_name,
            'userform-0-email': user.email,
            'userform-0-role': 'User',
        }
        if primary_group:
            post_data['userform-0-primary_group'] = 'on'
        self.client.force_login(self.proj_generalmanager if primary_group else self.pi_user)
        return self.client.post(self.url, data=post_data, follow=True)

    def _set_slurm_cluster(self, value='testcluster'):
        ResourceAttributeFactory(
            resource=self.cluster_resource,
            resource_attribute_type=ResourceAttributeType.objects.get(name='slurm_cluster'),
            value=value,
        )

    @patch('coldfront.core.project.views.allocation_remove_user.send')
    @patch('coldfront.core.project.views.allocation_user_remove_on_slurm.send_robust')
    @patch('coldfront.core.project.views.project_preremove_projectuser.send')
    @patch('coldfront.core.project.views.project_filter_users_to_remove.send')
    def test_projectuser_removal_removes_cluster_allocationuser(
        self, mock_filter, mock_preremove, mock_slurm_remove, mock_alloc_remove
    ):
        """Removing a ProjectUser removes their Slurm association and cluster AllocationUser"""
        self._set_slurm_cluster()
        cluster_alloc_user = self.cluster_allocation.allocationuser_set.get(user=self.project_user)
        status_at_signal = []

        def slurm_remove(**kwargs):
            # the Slurm removal must happen before the AllocationUser status changes
            cluster_alloc_user.refresh_from_db()
            status_at_signal.append(cluster_alloc_user.status.name)
            return [(None, None), (None, True)]
        mock_slurm_remove.side_effect = slurm_remove

        response = self._post_cluster_user_removal(mock_filter)

        mock_slurm_remove.assert_called_once_with(
            sender=ProjectRemoveUsersView,
            account=self.project.title,
            username=self.project_user.username,
            cluster='testcluster',
        )
        self.assertEqual(status_at_signal, ['Active'])
        cluster_alloc_user.refresh_from_db()
        self.assertEqual(cluster_alloc_user.status.name, 'Removed')
        mock_alloc_remove.assert_any_call(
            sender=ProjectRemoveUsersView, allocation_user_pk=cluster_alloc_user.pk
        )
        self.assertContains(
            response, f'Removed {self.project_user.username} from {self.cluster_resource.name} allocation.'
        )

    @patch('coldfront.core.project.views.allocation_remove_user.send')
    @patch('coldfront.core.project.views.allocation_user_remove_on_slurm.send_robust')
    @patch('coldfront.core.project.views.project_preremove_projectuser.send')
    @patch('coldfront.core.project.views.project_filter_users_to_remove.send')
    def test_projectuser_removal_slurm_failure_keeps_cluster_allocationuser(
        self, mock_filter, mock_preremove, mock_slurm_remove, mock_alloc_remove
    ):
        """A failed Slurm removal is reported and leaves the cluster AllocationUser Active,
        but the ProjectUser and storage AllocationUser are still removed"""
        self._set_slurm_cluster()
        mock_slurm_remove.return_value = [(None, Exception('user has running jobs'))]

        response = self._post_cluster_user_removal(mock_filter)

        cluster_alloc_user = self.cluster_allocation.allocationuser_set.get(user=self.project_user)
        self.assertEqual(cluster_alloc_user.status.name, 'Active')
        storage_alloc_user = self.storage_allocation.allocationuser_set.get(user=self.project_user)
        self.assertEqual(storage_alloc_user.status.name, 'Removed')
        self.assertEqual(ProjectUser.objects.get(pk=self.npu.pk).status.name, 'Removed')
        self.assertContains(
            response,
            f'Could not remove {self.project_user.username} from Slurm account {self.project.title} '
            f'on {self.cluster_resource.name}: user has running jobs. Their {self.cluster_resource.name} '
            'allocation membership was left active.',
        )
        self.assertNotIn(
            call(sender=ProjectRemoveUsersView, allocation_user_pk=cluster_alloc_user.pk),
            mock_alloc_remove.call_args_list,
        )

    @patch('coldfront.core.project.views.allocation_remove_user.send')
    @patch('coldfront.core.project.views.allocation_user_remove_on_slurm.send_robust')
    @patch('coldfront.core.project.views.project_preremove_projectuser.send')
    @patch('coldfront.core.project.views.project_filter_users_to_remove.send')
    def test_projectuser_deactivation_leaves_cluster_allocationuser_active(
        self, mock_filter, mock_preremove, mock_slurm_remove, mock_alloc_remove
    ):
        """Deactivating a user (primary group) makes no Slurm call and leaves their cluster
        AllocationUser Active; their storage AllocationUser is still removed"""
        self._set_slurm_cluster()

        response = self._post_cluster_user_removal(mock_filter, primary_group=True)

        self.assertEqual(ProjectUser.objects.get(pk=self.npu.pk).status.name, 'Deactivated')
        mock_slurm_remove.assert_not_called()
        cluster_alloc_user = self.cluster_allocation.allocationuser_set.get(user=self.project_user)
        self.assertEqual(cluster_alloc_user.status.name, 'Active')
        storage_alloc_user = self.storage_allocation.allocationuser_set.get(user=self.project_user)
        self.assertEqual(storage_alloc_user.status.name, 'Removed')
        msgs = [(m.level_tag, m.message) for m in response.context['messages']]
        self.assertFalse([m for tag, m in msgs if tag in ('error', 'warning')], msgs)

    @patch('coldfront.core.project.views.allocation_remove_user.send')
    @patch('coldfront.core.project.views.allocation_user_remove_on_slurm.send_robust')
    @patch('coldfront.core.project.views.project_preremove_projectuser.send')
    @patch('coldfront.core.project.views.project_filter_users_to_remove.send')
    def test_projectuser_removal_no_slurm_receiver_acts_keeps_cluster_allocationuser(
        self, mock_filter, mock_preremove, mock_slurm_remove, mock_alloc_remove
    ):
        """If no Slurm receiver confirms the removal (no matching integration),
        the cluster AllocationUser stays Active and the remover is told why"""
        self._set_slurm_cluster()
        mock_slurm_remove.return_value = [(None, None), (None, None)]

        response = self._post_cluster_user_removal(mock_filter)

        cluster_alloc_user = self.cluster_allocation.allocationuser_set.get(user=self.project_user)
        self.assertEqual(cluster_alloc_user.status.name, 'Active')
        self.assertContains(response, 'no Slurm integration is configured for cluster testcluster')
        self.assertNotContains(
            response, f'Removed {self.project_user.username} from {self.cluster_resource.name} allocation.'
        )

    @patch('coldfront.core.project.views.allocation_remove_user.send')
    @patch('coldfront.core.project.views.allocation_user_remove_on_slurm.send_robust')
    @patch('coldfront.core.project.views.project_preremove_projectuser.send')
    @patch('coldfront.core.project.views.project_filter_users_to_remove.send')
    def test_projectuser_removal_cluster_without_slurm_cluster_skips_signal(
        self, mock_filter, mock_preremove, mock_slurm_remove, mock_alloc_remove
    ):
        """A cluster resource with no slurm_cluster attribute gets no Slurm call,
        but the AllocationUser is still marked Removed"""
        self._post_cluster_user_removal(mock_filter)

        mock_slurm_remove.assert_not_called()
        cluster_alloc_user = self.cluster_allocation.allocationuser_set.get(user=self.project_user)
        self.assertEqual(cluster_alloc_user.status.name, 'Removed')


class ProjectUpdateViewTest(ProjectViewTestBase):
    """Tests for ProjectUpdateView"""
    def setUp(self):
        """set up users and project for testing"""
        self.url = f'/project/{self.project.pk}/update/'

    def test_projectupdateview_access(self):
        """test access to project update page"""
        self.project_access_tstbase(self.url)


class ProjectReviewListViewTest(ProjectViewTestBase):
    """Tests for ProjectReviewListView"""
    def setUp(self):
        """set up users and project for testing"""
        self.url = f'/project/project-review-list'

    def test_projectreviewlistview_access(self):
        """test access to project review list page"""
        self.project_access_tstbase(self.url)


class ProjectArchivedListViewTest(ProjectViewTestBase):
    """Tests for ProjectArchivedListView"""
    def setUp(self):
        """set up users and project for testing"""
        self.url = f'/project/archived/'

    def test_projectarchivedlistview_access(self):
        """test access to project archived list page"""
        self.project_access_tstbase(self.url)


class ProjectNoteCreateViewTest(ProjectViewTestBase):
    """Tests for ProjectNoteCreateView"""
    def setUp(self):
        """set up users and project for testing"""
        self.url = f'/project/{self.project.pk}/projectnote/add'

    def test_projectnotecreateview_access(self):
        """test access to project note create page"""
        self.project_access_tstbase(self.url)


class ProjectAddUsersSearchViewTest(ProjectViewTestBase):
    """Tests for ProjectAddUsersSearchView"""
    def setUp(self):
        """set up users and project for testing"""
        self.url = f'/project/{self.project.pk}/add-users-search/'

    def test_projectadduserssearchview_access(self):
        """test access to project add users search page"""
        self.project_access_tstbase(self.url)
        utils.test_user_can_access(self, self.pi_user, self.url)# pi can access
        utils.test_user_can_access(self, self.proj_accessmanager, self.url)# access manager can access
        utils.test_user_cannot_access(self, self.proj_datamanager, self.url)# data manager cannot access
        utils.test_user_cannot_access(self, self.proj_allocationuser, self.url)# user cannot access

@override_settings(ADDITIONAL_USER_SEARCH_CLASSES=[])  # search local users only, not LDAP
class ProjectAddUsersSearchResultsExternalTest(ProjectViewTestBase):
    """Tests for the External column on the add-users search results"""
    def setUp(self):
        self.url = reverse('project-add-users-search-results', kwargs={'pk': self.project.pk})
        self.external_user = UserFactory(username='ext_candidate')
        self.external_user.groups.add(Group.objects.get_or_create(name=EXTERNAL_USER_GROUPS[0])[0])
        self.internal_user = UserFactory(username='int_candidate')
        self.client.force_login(self.pi_user)

    def test_external_column_checks_only_external_users(self):
        response = self.client.post(self.url, data={
            'q': f'{self.external_user.username} {self.internal_user.username}',
            'search_by': 'username_only',
        })
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.content, 'html.parser')
        headers = [th.get_text(strip=True) for th in soup.find('thead').find_all('th')]
        self.assertEqual(headers.index('External'), headers.index('Email') + 1)
        external_col = headers.index('External')
        checked = {}
        for row in soup.find('tbody').find_all('tr'):
            cells = row.find_all('td')
            username = cells[headers.index('Username')].get_text(strip=True)
            checked[username] = cells[external_col].find('i', class_='fa-check') is not None
        self.assertEqual(checked, {self.external_user.username: True, self.internal_user.username: False})


@override_settings(ADDITIONAL_USER_SEARCH_CLASSES=[])  # search local users only, not LDAP
class ProjectAddUsersViewTest(ProjectViewTestBase):
    """Tests for ProjectAddUsersView"""
    def setUp(self):
        """set up users and project for testing"""
        self.url = reverse('project-add-users', kwargs={'pk': self.project.pk})
        self.form_data = {
            'q': self.nonproj_allocationuser.username,
            'search_by': 'username_only',
            'userform-TOTAL_FORMS': '1',
            'userform-INITIAL_FORMS': '0',
            'userform-MIN_NUM_FORMS': '0',
            'userform-MAX_NUM_FORMS': '1',
            'userform-0-selected': 'on',
            'userform-0-role': ProjectUserRoleChoice.objects.get(name='User').pk,
            'allocationform-allocation': [self.storage_allocation.pk]
        }

    @override_settings(PLUGIN_LDAP=True)
    def test_projectaddusers_ldapsignalfail_messages(self):
        """Test the messages displayed when the add user signal fails"""
        self.client.force_login(self.pi_user)

    @patch('coldfront.core.project.views.notify_manager_role_transition')
    @patch('coldfront.core.project.signals.project_make_projectuser.send')
    def test_projectaddusers_form_validation(self, mock_signal, mock_notify_transition):
        """Test that the formset and allocation form are validated correctly"""
        self.client.force_login(self.proj_accessmanager)
        mock_signal.return_value = None
        # Prepare form data for adding a user
        response = self.client.post(self.url, data=self.form_data)
        self.assertEqual(response.url, reverse('project-detail', kwargs={'pk': self.project.pk}))
        self.assertEqual(response.status_code, 302)
        # Check that user was added
        self.assertTrue(ProjectUser.objects.filter(project=self.project, user=self.nonproj_allocationuser).exists())

    @patch('coldfront.core.project.signals.project_make_projectuser.send')
    def test_projectaddusers_signal_fail(self, mock_signal):
        """Test that the add users form fails when the signal sent to LDAP fails"""
        self.client.force_login(self.proj_accessmanager)
        mock_signal.side_effect = Exception("LDAP error occurred")
        # Prepare form data for adding a user
        response = self.client.post(self.url, data=self.form_data, follow=True)
        # self.assertContains(response, 'LDAP error occurred')
        self.assertContains(response, 'Added 0 users')

    @patch('coldfront.core.project.views.EMAIL_SENDER', 'test-admin@coldfront.org')
    @patch('coldfront.core.utils.mail.EMAIL_ENABLED', True)
    @patch('coldfront.core.project.signals.project_make_projectuser.send')
    def test_projectaddusers_new_user_sends_added_email(self, mock_signal):
        """Adding a brand-new user sends a projectuser_added email to the
        user, cc'd to the PI."""
        self.client.force_login(self.proj_accessmanager)
        mock_signal.return_value = None
        self.client.post(self.url, data=self.form_data)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertIn(self.nonproj_allocationuser.email, sent.to)
        self.assertIn(self.pi_user.email, sent.cc)
        self.assertIn(self.nonproj_allocationuser.username, sent.subject)

    @patch('coldfront.core.project.views.EMAIL_SENDER', 'test-admin@coldfront.org')
    @patch('coldfront.core.utils.mail.EMAIL_ENABLED', True)
    @patch('coldfront.core.project.signals.project_make_projectuser.send')
    def test_projectaddusers_readd_removed_user_sends_added_email(self, mock_signal):
        """Re-adding a previously-Removed user also sends the added email,
        not just brand-new additions."""
        ProjectUserFactory(
            project=self.project, user=self.nonproj_allocationuser,
            status=ProjectUserStatusChoice.objects.get(name='Removed'),
        )
        self.client.force_login(self.proj_accessmanager)
        mock_signal.return_value = None
        self.client.post(self.url, data=self.form_data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.nonproj_allocationuser.email, mail.outbox[0].to)

    @patch('coldfront.core.project.views.EMAIL_SENDER', 'test-admin@coldfront.org')
    @patch('coldfront.core.utils.mail.EMAIL_ENABLED', True)
    @patch('coldfront.core.project.signals.project_reactivate_projectuser.send')
    def test_projectaddusers_reactivate_sends_reactivated_email(self, mock_signal):
        """Reactivating a Deactivated user sends a projectuser_reactivated
        email to the user, cc'd to the PI."""
        ProjectUserFactory(
            project=self.project, user=self.nonproj_allocationuser,
            status=ProjectUserStatusChoice.objects.get(name='Deactivated'),
        )
        mock_signal.return_value = None
        form_data = {
            'q': 'no_such_user_xyz',
            'search_by': 'username_only',
            'userform-TOTAL_FORMS': '0',
            'userform-INITIAL_FORMS': '0',
            'userform-MIN_NUM_FORMS': '0',
            'userform-MAX_NUM_FORMS': '0',
            'allocationform-allocation': [],
            'reactivateuserform-TOTAL_FORMS': '1',
            'reactivateuserform-INITIAL_FORMS': '1',
            'reactivateuserform-MIN_NUM_FORMS': '0',
            'reactivateuserform-MAX_NUM_FORMS': '1',
            'reactivateuserform-0-username': self.nonproj_allocationuser.username,
            'reactivateuserform-0-role': ProjectUserRoleChoice.objects.get(name='User').pk,
            'reactivateuserform-0-selected': 'on',
        }
        self.client.force_login(self.proj_accessmanager)
        self.client.post(self.url, data=form_data)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertIn(self.nonproj_allocationuser.email, sent.to)
        self.assertIn(self.pi_user.email, sent.cc)
        self.assertIn(self.nonproj_allocationuser.username, sent.subject)

    def _set_slurm_cluster(self, value='testcluster'):
        ResourceAttributeFactory(
            resource=self.cluster_resource,
            resource_attribute_type=ResourceAttributeType.objects.get(name='slurm_cluster'),
            value=value,
        )

    def _set_allocationuser_status(self, allocation, status_name):
        alloc_user = allocation.allocationuser_set.get(user=self.nonproj_allocationuser)
        alloc_user.status = AllocationUserStatusChoice.objects.get(name=status_name)
        alloc_user.save()
        return alloc_user

    def _post_cluster_user_addition(self):
        """Add nonproj_allocationuser to the project and its cluster allocation"""
        form_data = {**self.form_data, 'allocationform-allocation': [self.cluster_allocation.pk]}
        self.client.force_login(self.proj_accessmanager)
        return self.client.post(self.url, data=form_data, follow=True)

    def _post_reactivation(self):
        """Reactivate nonproj_allocationuser, who has a Deactivated ProjectUser"""
        ProjectUserFactory(
            project=self.project, user=self.nonproj_allocationuser,
            status=ProjectUserStatusChoice.objects.get(name='Deactivated'),
        )
        form_data = {
            'q': 'no_such_user_xyz',
            'search_by': 'username_only',
            'userform-TOTAL_FORMS': '0',
            'userform-INITIAL_FORMS': '0',
            'userform-MIN_NUM_FORMS': '0',
            'userform-MAX_NUM_FORMS': '0',
            'allocationform-allocation': [],
            'reactivateuserform-TOTAL_FORMS': '1',
            'reactivateuserform-INITIAL_FORMS': '1',
            'reactivateuserform-MIN_NUM_FORMS': '0',
            'reactivateuserform-MAX_NUM_FORMS': '1',
            'reactivateuserform-0-username': self.nonproj_allocationuser.username,
            'reactivateuserform-0-role': ProjectUserRoleChoice.objects.get(name='User').pk,
            'reactivateuserform-0-selected': 'on',
        }
        self.client.force_login(self.proj_accessmanager)
        return self.client.post(self.url, data=form_data, follow=True)

    @patch('coldfront.core.project.views.allocation_activate_user.send')
    @patch('coldfront.core.project.views.allocation_user_add_on_slurm.send_robust')
    @patch('coldfront.core.project.views.notify_manager_role_transition')
    @patch('coldfront.core.project.signals.project_make_projectuser.send')
    def test_projectaddusers_cluster_adds_slurm_association_before_activating(
        self, mock_make_pu, mock_notify, mock_slurm_add, mock_activate
    ):
        """Adding a user to a cluster allocation adds their Slurm association,
        then marks the AllocationUser Active and sends allocation_activate_user"""
        self._set_slurm_cluster()
        cluster_alloc_user = self._set_allocationuser_status(self.cluster_allocation, 'Removed')
        status_at_signal = []

        def slurm_add(**kwargs):
            # the Slurm addition must happen before the AllocationUser status changes
            cluster_alloc_user.refresh_from_db()
            status_at_signal.append(cluster_alloc_user.status.name)
            return [(None, None), (None, True)]
        mock_slurm_add.side_effect = slurm_add

        self._post_cluster_user_addition()

        mock_slurm_add.assert_called_once_with(
            sender=ProjectAddUsersView,
            username=self.nonproj_allocationuser.username,
            account=self.project.title,
            cluster='testcluster',
        )
        self.assertEqual(status_at_signal, ['Removed'])
        cluster_alloc_user.refresh_from_db()
        self.assertEqual(cluster_alloc_user.status.name, 'Active')
        mock_activate.assert_called_once_with(
            sender=ProjectAddUsersView, allocation_user_pk=cluster_alloc_user.pk
        )

    @patch('coldfront.core.project.views.allocation_activate_user.send')
    @patch('coldfront.core.project.views.allocation_user_add_on_slurm.send_robust')
    @patch('coldfront.core.project.views.notify_manager_role_transition')
    @patch('coldfront.core.project.signals.project_make_projectuser.send')
    def test_projectaddusers_cluster_slurm_error_leaves_allocationuser(
        self, mock_make_pu, mock_notify, mock_slurm_add, mock_activate
    ):
        """A Slurm receiver error is reported and the cluster AllocationUser is left as-is,
        but the ProjectUser is still added"""
        self._set_slurm_cluster()
        cluster_alloc_user = self._set_allocationuser_status(self.cluster_allocation, 'Removed')
        mock_slurm_add.return_value = [(None, Exception('slurmdbd unreachable'))]

        response = self._post_cluster_user_addition()

        cluster_alloc_user.refresh_from_db()
        self.assertEqual(cluster_alloc_user.status.name, 'Removed')
        mock_activate.assert_not_called()
        self.assertContains(response, 'slurmdbd unreachable')
        self.assertEqual(
            ProjectUser.objects.get(project=self.project, user=self.nonproj_allocationuser).status.name,
            'Active',
        )

    @patch('coldfront.core.project.views.allocation_activate_user.send')
    @patch('coldfront.core.project.views.allocation_user_add_on_slurm.send_robust')
    @patch('coldfront.core.project.views.notify_manager_role_transition')
    @patch('coldfront.core.project.signals.project_make_projectuser.send')
    def test_projectaddusers_cluster_no_slurm_receiver_acts_leaves_allocationuser(
        self, mock_make_pu, mock_notify, mock_slurm_add, mock_activate
    ):
        """If no Slurm receiver confirms the addition, the cluster AllocationUser is
        not activated and the person adding the user is told why"""
        self._set_slurm_cluster()
        cluster_alloc_user = self._set_allocationuser_status(self.cluster_allocation, 'Removed')
        mock_slurm_add.return_value = [(None, None), (None, None)]

        response = self._post_cluster_user_addition()

        cluster_alloc_user.refresh_from_db()
        self.assertEqual(cluster_alloc_user.status.name, 'Removed')
        mock_activate.assert_not_called()
        self.assertContains(response, 'no Slurm integration is configured for cluster testcluster')

    @patch('coldfront.core.project.views.allocation_activate_user.send')
    @patch('coldfront.core.project.views.allocation_user_add_on_slurm.send_robust')
    @patch('coldfront.core.project.views.notify_manager_role_transition')
    @patch('coldfront.core.project.signals.project_make_projectuser.send')
    def test_projectaddusers_cluster_without_slurm_cluster_skips_signal(
        self, mock_make_pu, mock_notify, mock_slurm_add, mock_activate
    ):
        """A cluster resource with no slurm_cluster attribute gets no Slurm call,
        but the AllocationUser is still activated"""
        cluster_alloc_user = self._set_allocationuser_status(self.cluster_allocation, 'Removed')

        self._post_cluster_user_addition()

        mock_slurm_add.assert_not_called()
        cluster_alloc_user.refresh_from_db()
        self.assertEqual(cluster_alloc_user.status.name, 'Active')
        mock_activate.assert_called_once_with(
            sender=ProjectAddUsersView, allocation_user_pk=cluster_alloc_user.pk
        )

    @patch('coldfront.core.project.views.allocation_activate_user.send')
    @patch('coldfront.core.project.views.allocation_user_add_on_slurm.send_robust')
    @patch('coldfront.core.project.signals.project_reactivate_projectuser.send')
    def test_projectaddusers_reactivate_leaves_cluster_allocationuser_alone(
        self, mock_reactivate_pu, mock_slurm_add, mock_activate
    ):
        """Reactivation makes no Slurm call and doesn't touch cluster AllocationUsers;
        slurmrest_sync keeps their status in line with Slurm"""
        self._set_slurm_cluster()
        cluster_alloc_user = self._set_allocationuser_status(self.cluster_allocation, 'Removed')

        self._post_reactivation()

        cluster_alloc_user.refresh_from_db()
        self.assertEqual(cluster_alloc_user.status.name, 'Removed')
        mock_slurm_add.assert_not_called()
        mock_activate.assert_not_called()

    @patch('coldfront.core.project.views.allocation_activate_user.send')
    @patch('coldfront.core.project.views.allocation_user_add_on_slurm.send_robust')
    @patch('coldfront.core.project.signals.project_reactivate_projectuser.send')
    def test_projectaddusers_reactivate_storage_only_unchanged(
        self, mock_reactivate_pu, mock_slurm_add, mock_activate
    ):
        """Reactivation restores storage AllocationUsers and makes no Slurm call"""
        self._set_slurm_cluster()
        storage_alloc_user = self._set_allocationuser_status(self.storage_allocation, 'Removed')

        self._post_reactivation()

        storage_alloc_user.refresh_from_db()
        self.assertEqual(storage_alloc_user.status.name, 'Active')
        mock_slurm_add.assert_not_called()
        mock_activate.assert_not_called()


class ProjectUserDetailViewTest(ProjectViewTestBase):
    """Tests for ProjectUserDetailView"""
    def setUp(self):
        """set up users and project for testing"""
        self.url = f'/project/{self.project.pk}/user-detail/{self.project_user.pk}'

    def test_projectuserdetailview_access(self):
        """test access to project user detail page"""
        self.project_access_tstbase(self.url)
        utils.test_user_can_access(self, self.pi_user, self.url)# pi can access
        utils.test_user_can_access(self, self.proj_generalmanager, self.url) # general manager can access
        utils.test_user_cannot_access(self, self.proj_accessmanager, self.url)# access manager cannot access
        utils.test_user_cannot_access(self, self.proj_datamanager, self.url)# storage manager cannot access

    def test_projectuserdetailview_deactivated_unreachable(self):
        """A Deactivated ProjectUser's edit page is unreachable, even to a
        General Manager who could otherwise edit any non-PI user."""
        self.npu.status = ProjectUserStatusChoice.objects.get(name='Deactivated')
        self.npu.save()
        url = reverse(
            'project-user-detail',
            kwargs={'pk': self.project.pk, 'project_user_pk': self.npu.pk},
        )
        utils.test_user_cannot_access(self, self.proj_generalmanager, url)

    def test_projectuserdetailview_deactivated_post_rejected(self):
        """POSTing a role/notification change for a Deactivated ProjectUser is
        rejected and leaves the row unchanged."""
        deactivated_status = ProjectUserStatusChoice.objects.get(name='Deactivated')
        self.npu.status = deactivated_status
        self.npu.save()
        original_role = self.npu.role
        url = reverse(
            'project-user-detail',
            kwargs={'pk': self.project.pk, 'project_user_pk': self.npu.pk},
        )
        other_role = ProjectUserRoleChoice.objects.exclude(
            pk=original_role.pk
        ).exclude(name='PI').first()
        self.client.force_login(self.proj_generalmanager)
        self.client.post(url, data={'role': other_role.pk, 'enable_notifications': 'on'})
        self.npu.refresh_from_db()
        self.assertEqual(self.npu.role, original_role)
        self.assertEqual(self.npu.status, deactivated_status)

    def test_projectuserdetailview_role_options(self):
        """Only Admin and PI should see option to set role to General Manager;
        option to set role to PI should not be available"""
        self.client.force_login(self.admin_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('project_user_update_form', response.context)
        form = response.context['project_user_update_form']
        self.assertIn('role', form.fields)
        role_field = form.fields['role']
        role_names = [role.name for role in role_field.choices.queryset]
        self.assertNotIn('PI', role_names)
        self.assertIn('General Manager', role_names)
        self.assertIn('Access Manager', role_names)
        self.assertIn('Storage Manager', role_names)

        self.client.force_login(self.pi_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('project_user_update_form', response.context)
        form = response.context['project_user_update_form']
        self.assertIn('role', form.fields)
        role_field = form.fields['role']
        role_names = [role.name for role in role_field.choices.queryset]
        self.assertNotIn('PI', role_names)
        self.assertIn('General Manager', role_names)
        self.assertIn('Access Manager', role_names)
        self.assertIn('Storage Manager', role_names)

        self.client.force_login(self.proj_generalmanager)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('project_user_update_form', response.context)
        form = response.context['project_user_update_form']
        self.assertIn('role', form.fields)
        role_field = form.fields['role']
        role_names = [role.name for role in role_field.choices.queryset]
        self.assertNotIn('PI', role_names)
        self.assertNotIn('General Manager', role_names)
        self.assertIn('Access Manager', role_names)
        self.assertIn('Storage Manager', role_names)


class ProjectUserDetailExpirationTest(ProjectViewTestBase):
    """Tests for editing an external user's expiration on ProjectUserDetail"""
    def setUp(self):
        self.url = reverse(
            'project-user-detail',
            kwargs={'pk': self.project.pk, 'project_user_pk': self.npu.pk},
        )
        self.target = self.npu.user
        self.target.expiration = None
        self.target.save()
        # Non-external users can only have expiration set from their primary project.
        self.npu.primary_group = True
        self.npu.save()
        self.client.force_login(self.proj_generalmanager)
        # The ldap plugin's receiver pushes expiration to AD; mock the connection.
        patcher = patch('coldfront.plugins.ldap.signals.LDAPConn')
        self.mock_ldapconn = patcher.start()
        self.addCleanup(patcher.stop)
        self.mock_set_expiration = self.mock_ldapconn.return_value.set_user_expiration

    def make_external(self, group_name=EXTERNAL_USER_GROUPS[0]):
        self.target.groups.add(Group.objects.get_or_create(name=group_name)[0])

    def post_data(self, expiration):
        return {
            'role': self.npu.role.pk,
            'enable_notifications': 'on',
            'expiration': expiration.isoformat() if expiration else '',
        }

    def test_expiration_field_optional_when_user_not_external(self):
        response = self.client.get(self.url)
        fields = response.context['project_user_update_form'].fields
        self.assertIn('expiration', fields)
        self.assertFalse(fields['expiration'].required)
        self.assertNotIn('max', fields['expiration'].widget.attrs)
        self.assertNotIn('min', fields['expiration'].widget.attrs)

    def test_expiration_picker_limited_to_allowed_range_for_external_user(self):
        self.make_external()
        soup = BeautifulSoup(self.client.get(self.url).content, 'html.parser')
        date_input = soup.find('input', {'name': 'expiration'})
        today = timezone.localdate()
        self.assertEqual(date_input['min'], (today + datetime.timedelta(days=1)).isoformat())
        self.assertEqual(
            date_input['max'], (today + datetime.timedelta(days=EXTERNAL_EXPIRATION_MAX_DAYS)).isoformat()
        )

    def test_expiration_field_shown_when_user_external(self):
        self.make_external()
        response = self.client.get(self.url)
        self.assertIn('expiration', response.context['project_user_update_form'].fields)

    def test_expiration_post_at_max_days_saves(self):
        self.make_external()
        new_date = timezone.localdate() + datetime.timedelta(days=EXTERNAL_EXPIRATION_MAX_DAYS)
        self.client.post(self.url, data=self.post_data(new_date))
        self.target.refresh_from_db()
        self.assertEqual(timezone.localdate(self.target.expiration), new_date)

    def test_expiration_post_pushes_to_ad(self):
        self.make_external()
        new_date = timezone.localdate() + datetime.timedelta(days=30)
        self.client.post(self.url, data=self.post_data(new_date))
        self.mock_set_expiration.assert_called_once()
        args, kwargs = self.mock_set_expiration.call_args
        self.assertEqual(args[0], self.target.username)
        self.assertEqual(timezone.localdate(args[1]), new_date)
        self.assertEqual(kwargs['actor_username'], self.proj_generalmanager.username)

    def test_expiration_ad_failure_saves_nothing(self):
        """If AD rejects the write, neither the expiration nor other fields are saved."""
        self.make_external()
        self.npu.enable_notifications = True
        self.npu.save()
        self.mock_set_expiration.side_effect = Exception('insufficientAccessRights')
        new_date = timezone.localdate() + datetime.timedelta(days=30)
        data = self.post_data(new_date)
        del data['enable_notifications']
        response = self.client.post(self.url, data=data, follow=True)
        self.target.refresh_from_db()
        self.npu.refresh_from_db()
        self.assertIsNone(self.target.expiration)
        self.assertTrue(self.npu.enable_notifications)
        self.assertContains(response, 'Could not update the account expiration in AD')

    def test_expiration_unchanged_within_cap_saves_other_fields_without_ad_push(self):
        self.make_external()
        existing = timezone.now() + datetime.timedelta(days=30)
        self.target.expiration = existing
        self.target.save()
        self.npu.enable_notifications = True
        self.npu.save()
        data = self.post_data(timezone.localdate(existing))
        del data['enable_notifications']
        self.client.post(self.url, data=data)
        self.npu.refresh_from_db()
        self.target.refresh_from_db()
        self.assertFalse(self.npu.enable_notifications)
        self.assertEqual(self.target.expiration, existing)
        self.mock_set_expiration.assert_not_called()

    def test_expiration_post_over_max_days_rejected(self):
        self.make_external()
        new_date = timezone.localdate() + datetime.timedelta(days=EXTERNAL_EXPIRATION_MAX_DAYS + 1)
        self.client.post(self.url, data=self.post_data(new_date))
        self.target.refresh_from_db()
        self.assertIsNone(self.target.expiration)
        self.mock_set_expiration.assert_not_called()

    def test_expiration_post_past_date_rejected(self):
        self.make_external()
        new_date = timezone.localdate() - datetime.timedelta(days=1)
        self.client.post(self.url, data=self.post_data(new_date))
        self.target.refresh_from_db()
        self.assertIsNone(self.target.expiration)

    def make_non_primary(self):
        self.npu.primary_group = False
        self.npu.save()

    def test_non_external_expiration_field_hidden_outside_primary_project(self):
        self.make_non_primary()
        existing = timezone.now() + datetime.timedelta(days=200)
        self.target.expiration = existing
        self.target.save()
        response = self.client.get(self.url)
        self.assertNotIn('expiration', response.context['project_user_update_form'].fields)
        self.assertContains(response, timezone.localdate(existing).isoformat())
        self.assertContains(response, "can only be changed from the user's primary project")

    def test_non_external_expiration_post_ignored_outside_primary_project(self):
        self.make_non_primary()
        existing = timezone.now() + datetime.timedelta(days=200)
        self.target.expiration = existing
        self.target.save()
        self.npu.enable_notifications = True
        self.npu.save()
        new_date = timezone.localdate() + datetime.timedelta(days=30)
        data = self.post_data(new_date)
        del data['enable_notifications']
        self.client.post(self.url, data=data)
        self.target.refresh_from_db()
        self.npu.refresh_from_db()
        self.assertEqual(self.target.expiration, existing)
        self.assertFalse(self.npu.enable_notifications)
        self.mock_set_expiration.assert_not_called()

    def test_non_external_blank_post_outside_primary_project_does_not_clear(self):
        self.make_non_primary()
        existing = timezone.now() + datetime.timedelta(days=200)
        self.target.expiration = existing
        self.target.save()
        self.client.post(self.url, data=self.post_data(None))
        self.target.refresh_from_db()
        self.assertEqual(self.target.expiration, existing)
        self.mock_set_expiration.assert_not_called()

    def test_external_expiration_not_settable_outside_primary_project(self):
        self.make_non_primary()
        self.make_external()
        response = self.client.get(self.url)
        self.assertNotIn('expiration', response.context['project_user_update_form'].fields)
        self.assertContains(response, "can only be changed from the user's primary project")
        new_date = timezone.localdate() + datetime.timedelta(days=30)
        self.client.post(self.url, data=self.post_data(new_date))
        self.target.refresh_from_db()
        self.assertIsNone(self.target.expiration)
        self.mock_set_expiration.assert_not_called()

    def test_non_external_expiration_over_max_days_saves_and_pushes_to_ad(self):
        new_date = timezone.localdate() + datetime.timedelta(days=EXTERNAL_EXPIRATION_MAX_DAYS + 100)
        self.client.post(self.url, data=self.post_data(new_date))
        self.target.refresh_from_db()
        self.assertEqual(timezone.localdate(self.target.expiration), new_date)
        self.mock_set_expiration.assert_called_once()
        self.assertEqual(self.mock_set_expiration.call_args.args[0], self.target.username)

    def test_non_external_blank_expiration_saves_other_fields(self):
        self.npu.enable_notifications = True
        self.npu.save()
        data = self.post_data(None)
        del data['enable_notifications']
        self.client.post(self.url, data=data)
        self.npu.refresh_from_db()
        self.target.refresh_from_db()
        self.assertFalse(self.npu.enable_notifications)
        self.assertIsNone(self.target.expiration)
        self.mock_set_expiration.assert_not_called()

    def test_non_external_blank_expiration_clears_existing_and_pushes_to_ad(self):
        existing = timezone.now() + datetime.timedelta(days=200)
        self.target.expiration = existing
        self.target.save()
        self.client.post(self.url, data=self.post_data(None))
        self.target.refresh_from_db()
        self.assertIsNone(self.target.expiration)
        self.mock_set_expiration.assert_called_once()
        self.assertEqual(self.mock_set_expiration.call_args.args, (self.target.username, None))

    def test_non_external_clear_ad_failure_keeps_existing(self):
        existing = timezone.now() + datetime.timedelta(days=200)
        self.target.expiration = existing
        self.target.save()
        self.mock_set_expiration.side_effect = Exception('insufficientAccessRights')
        self.client.post(self.url, data=self.post_data(None))
        self.target.refresh_from_db()
        self.assertEqual(self.target.expiration, existing)

    def test_non_external_unchanged_past_expiration_accepted(self):
        """An already-expired date left as is doesn't block other updates."""
        existing = timezone.now() - datetime.timedelta(days=5)
        self.target.expiration = existing
        self.target.save()
        self.npu.enable_notifications = True
        self.npu.save()
        data = self.post_data(timezone.localdate(existing))
        del data['enable_notifications']
        self.client.post(self.url, data=data)
        self.npu.refresh_from_db()
        self.assertFalse(self.npu.enable_notifications)
        self.mock_set_expiration.assert_not_called()

    def test_non_external_past_expiration_rejected(self):
        new_date = timezone.localdate() - datetime.timedelta(days=1)
        self.client.post(self.url, data=self.post_data(new_date))
        self.target.refresh_from_db()
        self.assertIsNone(self.target.expiration)
        self.mock_set_expiration.assert_not_called()

    @override_settings(LANGUAGE_CODE='en-gb')
    def test_existing_expiration_renders_as_iso_date_in_any_locale(self):
        existing = timezone.now() + datetime.timedelta(days=45)
        self.target.expiration = existing
        self.target.save()
        response = self.client.get(self.url)
        self.assertContains(response, f'value="{timezone.localdate(existing).isoformat()}"')

    def test_external_badge_shown_next_to_username(self):
        self.make_external()
        soup = BeautifulSoup(self.client.get(self.url).content, 'html.parser')
        username_cell = soup.find('th', string='Username:').find_next_sibling('td')
        self.assertEqual(username_cell.find('span', class_='badge').get_text(strip=True), 'External')

    def test_no_external_badge_for_non_external_user(self):
        soup = BeautifulSoup(self.client.get(self.url).content, 'html.parser')
        username_cell = soup.find('th', string='Username:').find_next_sibling('td')
        self.assertIsNone(username_cell.find('span', class_='badge'))

    def test_expiration_optional_for_external_user(self):
        self.make_external()
        response = self.client.get(self.url)
        self.assertFalse(response.context['project_user_update_form'].fields['expiration'].required)

    def test_every_external_group_gets_external_rules(self):
        for group_name in EXTERNAL_USER_GROUPS:
            with self.subTest(group=group_name):
                max_days = (
                    VENDOR_EXPIRATION_MAX_DAYS if group_name == VENDOR_USER_GROUP
                    else EXTERNAL_EXPIRATION_MAX_DAYS
                )
                max_date = timezone.localdate() + datetime.timedelta(days=max_days)
                self.target.groups.clear()
                self.make_external(group_name)
                response = self.client.get(self.url)
                form = response.context['project_user_update_form']
                self.assertTrue(form.is_external)
                self.assertEqual(form.fields['expiration'].widget.attrs['max'], max_date.isoformat())

    def make_vendor(self):
        self.target.groups.add(Group.objects.get_or_create(name=VENDOR_USER_GROUP)[0])

    def test_vendor_picker_limited_to_vendor_max_days(self):
        self.make_vendor()
        soup = BeautifulSoup(self.client.get(self.url).content, 'html.parser')
        date_input = soup.find('input', {'name': 'expiration'})
        today = timezone.localdate()
        self.assertEqual(date_input['min'], (today + datetime.timedelta(days=1)).isoformat())
        self.assertEqual(
            date_input['max'], (today + datetime.timedelta(days=VENDOR_EXPIRATION_MAX_DAYS)).isoformat()
        )

    def test_vendor_expiration_at_vendor_max_days_saves(self):
        self.make_vendor()
        new_date = timezone.localdate() + datetime.timedelta(days=VENDOR_EXPIRATION_MAX_DAYS)
        self.client.post(self.url, data=self.post_data(new_date))
        self.target.refresh_from_db()
        self.assertEqual(timezone.localdate(self.target.expiration), new_date)

    def test_vendor_expiration_over_vendor_max_days_rejected(self):
        self.make_vendor()
        new_date = timezone.localdate() + datetime.timedelta(days=VENDOR_EXPIRATION_MAX_DAYS + 1)
        response = self.client.post(self.url, data=self.post_data(new_date), follow=True)
        self.target.refresh_from_db()
        self.assertIsNone(self.target.expiration)
        self.assertContains(response, f'cannot be more than {VENDOR_EXPIRATION_MAX_DAYS} days')
        self.mock_set_expiration.assert_not_called()

    def test_vendor_past_expiration_rejected(self):
        self.make_vendor()
        new_date = timezone.localdate() - datetime.timedelta(days=1)
        self.client.post(self.url, data=self.post_data(new_date))
        self.target.refresh_from_db()
        self.assertIsNone(self.target.expiration)

    def test_vendor_unchanged_over_vendor_max_days_rejected_and_saves_nothing(self):
        """An existing vendor expiration beyond the vendor limit must be brought within
        it before any other update is saved."""
        self.make_vendor()
        existing = timezone.now() + datetime.timedelta(days=VENDOR_EXPIRATION_MAX_DAYS + 10)
        self.target.expiration = existing
        self.target.save()
        self.npu.enable_notifications = True
        self.npu.save()
        data = self.post_data(timezone.localdate(existing))
        del data['enable_notifications']
        self.client.post(self.url, data=data)
        self.npu.refresh_from_db()
        self.target.refresh_from_db()
        self.assertTrue(self.npu.enable_notifications)
        self.assertEqual(self.target.expiration, existing)
        self.mock_set_expiration.assert_not_called()

    def test_vendor_not_settable_outside_primary_project(self):
        self.make_non_primary()
        self.make_vendor()
        response = self.client.get(self.url)
        self.assertNotIn('expiration', response.context['project_user_update_form'].fields)

    def test_user_in_external_and_vendor_groups_gets_vendor_limit(self):
        self.make_external()
        self.make_vendor()
        form = self.client.get(self.url).context['project_user_update_form']
        self.assertEqual(form.max_days, VENDOR_EXPIRATION_MAX_DAYS)

    def test_external_blank_expiration_saves_other_fields(self):
        """A blank expiration for an external user with none set is accepted, and other changes save."""
        self.make_external()
        self.npu.enable_notifications = True
        self.npu.save()
        data = self.post_data(None)
        del data['enable_notifications']
        self.client.post(self.url, data=data)
        self.npu.refresh_from_db()
        self.target.refresh_from_db()
        self.assertFalse(self.npu.enable_notifications)
        self.assertIsNone(self.target.expiration)
        self.mock_set_expiration.assert_not_called()

    def test_external_blank_expiration_clears_existing_and_pushes_to_ad(self):
        self.make_external()
        self.target.expiration = timezone.now() + datetime.timedelta(days=30)
        self.target.save()
        self.client.post(self.url, data=self.post_data(None))
        self.target.refresh_from_db()
        self.assertIsNone(self.target.expiration)
        self.mock_set_expiration.assert_called_once()
        self.assertEqual(self.mock_set_expiration.call_args.args, (self.target.username, None))

    def test_expiration_unchanged_over_cap_rejected_and_saves_nothing(self):
        """An existing expiration beyond the cap (e.g. synced from AD) must be
        brought within EXTERNAL_EXPIRATION_MAX_DAYS before any other update is saved."""
        self.make_external()
        existing = timezone.now() + datetime.timedelta(days=EXTERNAL_EXPIRATION_MAX_DAYS + 100)
        self.target.expiration = existing
        self.target.save()
        self.npu.enable_notifications = True
        self.npu.save()
        data = self.post_data(timezone.localdate(existing))
        del data['enable_notifications']
        response = self.client.post(self.url, data=data, follow=True)
        self.npu.refresh_from_db()
        self.target.refresh_from_db()
        self.assertTrue(self.npu.enable_notifications)
        self.assertEqual(self.target.expiration, existing)
        self.assertContains(response, f'cannot be more than {EXTERNAL_EXPIRATION_MAX_DAYS} days')
        self.mock_set_expiration.assert_not_called()


class ProjectUpdateEmailNotificationTest(ProjectViewTestBase):
    """Tests for the project_update_email_notification AJAX endpoint"""

    def setUp(self):
        self.url = reverse('project-user-update-email-notification')

    def test_deactivated_projectuser_rejected_for_manager(self):
        """An Access Manager cannot toggle notifications for a Deactivated
        ProjectUser."""
        self.npu.status = ProjectUserStatusChoice.objects.get(name='Deactivated')
        self.npu.enable_notifications = True
        self.npu.save()
        self.client.force_login(self.proj_accessmanager)
        response = self.client.post(
            self.url, data={'user_project_id': self.npu.pk, 'checked': 'false'}
        )
        self.assertEqual(response.status_code, 403)
        self.npu.refresh_from_db()
        self.assertTrue(self.npu.enable_notifications)

    def test_deactivated_projectuser_rejected_for_self(self):
        """A Deactivated user cannot toggle their own notifications either."""
        self.npu.status = ProjectUserStatusChoice.objects.get(name='Deactivated')
        self.npu.enable_notifications = True
        self.npu.save()
        self.client.force_login(self.npu.user)
        response = self.client.post(
            self.url, data={'user_project_id': self.npu.pk, 'checked': 'false'}
        )
        self.assertEqual(response.status_code, 403)
        self.npu.refresh_from_db()
        self.assertTrue(self.npu.enable_notifications)
