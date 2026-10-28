import logging

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from unittest.mock import call, patch

from coldfront.core.test_helpers import utils
from coldfront.core.test_helpers.factories import (
    setup_models,
    ProjectFactory,
    ProjectUserFactory,
    PAttributeTypeFactory,
    ProjectAttributeFactory,
    ProjectStatusChoiceFactory,
    ProjectAttributeTypeFactory,
    ResourceAttributeFactory,
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

    @patch('coldfront.core.project.signals.project_reactivate_projectuser.send')
    def test_projectaddusers_reactivate_restores_other_group_projectusers(self, mock_reactivate_pu):
        """Reactivation restores the user's Removed/Deactivated ProjectUsers in active
        projects named by the group names the reactivate receivers return"""
        removed_pu = ProjectUserFactory(
            project=ProjectFactory(title='reactivate_removed_lab'), user=self.nonproj_allocationuser,
            status=ProjectUserStatusChoice.objects.get(name='Removed'),
        )
        deactivated_pu = ProjectUserFactory(
            project=ProjectFactory(title='reactivate_deactivated_lab'), user=self.nonproj_allocationuser,
            status=ProjectUserStatusChoice.objects.get(name='Deactivated'),
        )
        archived_pu = ProjectUserFactory(
            project=ProjectFactory(
                title='reactivate_archived_lab', status=ProjectStatusChoiceFactory(name='Archived')
            ),
            user=self.nonproj_allocationuser,
            status=ProjectUserStatusChoice.objects.get(name='Removed'),
        )
        outside_pu = ProjectUserFactory(
            project=ProjectFactory(title='reactivate_other_lab'), user=self.nonproj_allocationuser,
            status=ProjectUserStatusChoice.objects.get(name='Removed'),
        )
        mock_reactivate_pu.return_value = [(
            None, ['reactivate_removed_lab', 'reactivate_deactivated_lab', 'reactivate_archived_lab']
        )]

        self._post_reactivation()

        for projectuser, status in [
            (removed_pu, 'Active'), (deactivated_pu, 'Active'), (archived_pu, 'Removed'), (outside_pu, 'Removed')
        ]:
            projectuser.refresh_from_db()
            self.assertEqual(projectuser.status.name, status, projectuser.project.title)

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
