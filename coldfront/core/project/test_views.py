import logging

from django.core.exceptions import ValidationError
from django.test import TestCase, Client

from coldfront.core.test_helpers import utils
from coldfront.core.test_helpers.factories import (
    FieldOfScienceFactory,
    ProjectFactory,
    PAttributeTypeFactory,
    ProjectAttributeFactory,
    ProjectUserFactory,
    ProjectAttributeTypeFactory,
    ProjectUserRoleChoiceFactory,
    ProjectStatusChoiceFactory,
    UserFactory,
    fake
)
from coldfront.core.project.models import ProjectUserStatusChoice

logging.disable(logging.CRITICAL)



class ProjectViewTestBase(TestCase):
    """Base class for project view tests"""
    
    @classmethod
    def setUpTestData(cls):
        """Set up users and project for testing"""
        cls.admin_user = UserFactory(username='gvanrossum', is_staff=True, is_superuser=True)
        cls.pi_user = UserFactory(username='sdpoisson', is_staff=False, is_superuser=False)
        cls.project_user = UserFactory(username='ljbortkiewicz', is_staff=False, is_superuser=False)
        cls.nonproject_user = UserFactory(username='wkohn', is_staff=False, is_superuser=False)
        cls.project = ProjectFactory(pi=cls.pi_user)
        manager_role = ProjectUserRoleChoiceFactory(name='Manager')
        # add pi_user and project_user to project_user
        pi_proj_user = ProjectUserFactory(project=cls.project, user=cls.pi_user,
                        role=manager_role)
        cls.normal_projuser = ProjectUserFactory(project=cls.project, user=cls.project_user)
 
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






class ProjectDetailViewTest(ProjectViewTestBase):
    """tests for ProjectDetailView"""

    @classmethod
    def setUpTestData(cls):
        """Set up users and project for testing"""
        super(ProjectDetailViewTest, cls).setUpTestData()
        cls.projectattribute = ProjectAttributeFactory(value=36238, 
                proj_attr_type=cls.projectattributetype, project=cls.project)
        cls.url = f'/project/{cls.project.pk}/'

    def setUp(self):
        self.client = Client()


    def test_project_detail_access(self):
        """Test project detail page access"""
        # logged-out user gets redirected, admin can access create page
        self.project_access_tstbase(self.url)
        # pi and projectuser can access
        utils.test_user_can_access(self, self.pi_user, self.url)
        utils.test_user_can_access(self, self.project_user, self.url)
        # user not belonging to project cannot access
        utils.test_user_cannot_access(self, self.nonproject_user, self.url)


    def test_project_detail_permissions(self):
        """Test project detail page access permissions"""
        # admin has is_allowed_to_update_project set to True
        response = utils.login_and_get_page(self.client, self.admin_user, self.url)
        self.assertEqual(response.context['is_allowed_to_update_project'], True)

        # pi has is_allowed_to_update_project set to True
        response = utils.login_and_get_page(self.client, self.pi_user, self.url)
        self.assertEqual(response.context['is_allowed_to_update_project'], True)

        # non-manager user has is_allowed_to_update_project set to False
        response = utils.login_and_get_page(self.client, self.project_user, self.url)
        self.assertEqual(response.context['is_allowed_to_update_project'], False)


    def test_project_detail_edit_button_visibility(self):
        """Test visibility of project detail edit button to different projectuser levels"""
        # admin can see edit button
        response = utils.login_and_get_page(self.client, self.admin_user, self.url)
        self.assertContains(response, 'fa-user-edit')

        # pi can see edit button
        response = utils.login_and_get_page(self.client, self.pi_user, self.url)
        self.assertContains(response, 'fa-user-edit')

        # non-manager user cannot see edit button
        response = utils.login_and_get_page(self.client, self.project_user, self.url)
        self.assertNotContains(response, 'fa-user-edit')




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
        # pi can access create page
        utils.test_user_can_access(self, self.pi_user, self.url)
        # project user and nonproject user cannot access create page
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
        response = self.client.post(self.url, data={'proj_attr_type': self.projectattributetype.pk,
                                                    'value': 'test_value'})
        self.assertFormError(response, 'form', 'project', 'This field is required.')
        # missing value
        response = self.client.post(self.url, data={'proj_attr_type': self.projectattributetype.pk,
                                                    'project': self.project.pk})
        self.assertFormError(response, 'form', 'value', 'This field is required.')


    def test_project_attribute_create_value_type_match(self):
        """ProjectAttributeCreate correctly flags value-type mismatch"""

        self.client.force_login(self.admin_user,
                    backend='django.contrib.auth.backends.ModelBackend')
        # test that value must be numeric if proj_attr_type is string
        response = self.client.post(self.url, data={'proj_attr_type': self.int_projectattributetype.pk,
                                                    'value': True,
                                                    'project': self.project.pk})
        self.assertFormError(response, 'form', '', 'Invalid Value True. Value must be an int.')



class ProjectAttributeUpdateTest(ProjectViewTestBase):

    @classmethod
    def setUpTestData(cls):
        """Set up users and project for testing"""
        super(ProjectAttributeUpdateTest, cls).setUpTestData()
        cls.projectattribute = ProjectAttributeFactory(value=36238, proj_attr_type=cls.projectattributetype, project=cls.project)
        cls.url = f'/project/{cls.project.pk}/project-attribute-update/{cls.projectattribute.pk}'

    def setUp(self):
        self.client = Client()


    def test_project_attribute_update_access(self):
        """Test access to project attribute update page"""
        self.project_access_tstbase(self.url)
        utils.test_user_can_access(self, self.pi_user, self.url)
        # project user, pi, and nonproject user cannot access update page
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
        # pi can access delete page
        utils.test_user_can_access(self, self.pi_user, self.url)
        # project user and nonproject user cannot access delete page
        utils.test_user_cannot_access(self, self.project_user, self.url)
        utils.test_user_cannot_access(self, self.nonproject_user, self.url)



class ProjectListViewTest(ProjectViewTestBase):
    """Tests for projectlist view"""

    @classmethod
    def setUpTestData(cls):
        """Set up users and project for testing"""
        super(ProjectListViewTest, cls).setUpTestData()
        # add 100 projects to test pagination, permissions, search functionality
        cls.additional_projects = [
                    ProjectFactory(title=fake.unique.project_title(),
                    pi=UserFactory(username=fake.unique.user_name()))
                for i in list(range(100))
                             ]
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
        self.normal_projuser.status, _ = ProjectUserStatusChoice.objects.get_or_create(name='Removed')
        self.normal_projuser.save()
        self.client.force_login(self.normal_projuser.user, backend='django.contrib.auth.backends.ModelBackend')
        response = self.client.get(self.url)
        self.assertEqual(len(response.context['object_list']), 0)

    def test_project_list_displayall_permission_admin(self):
        """Test that the projectlist displayall option displays all projects to admin"""
        url = self.url + '?show_all_projects=on'
        self.client.force_login(self.admin_user, backend='django.contrib.auth.backends.ModelBackend')
        response = self.client.get(url)
        self.assertGreaterEqual(25, len(response.context['object_list']))

    def test_project_list_displayall_permission_pi(self):
        """Test that the projectlist displayall option displays only the pi's projects to the pi"""
        url = self.url + '?show_all_projects=on'
        self.client.force_login(self.pi_user, backend='django.contrib.auth.backends.ModelBackend')
        response = self.client.get(url)
        self.assertEqual(len(response.context['object_list']), 1)

    def test_project_list_displayall_permission_project_user(self):
        """Test that the projectlist displayall option displays only the project user's projects to the project user"""
        url = self.url + '?show_all_projects=on'
        self.client.force_login(self.project_user, backend='django.contrib.auth.backends.ModelBackend')
        response = self.client.get(url)
        self.assertEqual(len(response.context['object_list']), 1)


    ### ProjectListView search tests ###

    def test_project_list_search(self):
        """Test that project list search works."""
        url_base = self.url + '?show_all_projects=on'
        self.client.force_login(self.admin_user, backend='django.contrib.auth.backends.ModelBackend')
        # search by project project_title
        url = url_base + '&title=' + self.project.title
        response = self.client.get(url)
        self.assertEqual(len(response.context['object_list']), 1)


    def test_project_list_search_pagination(self):
        """confirm that navigation to next page of search works as expected"""
        url = self.url + '?show_all_projects=on'
        self.client.force_login(self.admin_user, backend='django.contrib.auth.backends.ModelBackend')
        response = self.client.get(url)
