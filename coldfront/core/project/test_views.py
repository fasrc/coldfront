import logging

from django.test import TestCase

from coldfront.core.test_helpers import utils
from coldfront.core.test_helpers.factories import (
    UserFactory,
    ProjectFactory,
    ProjectUserFactory,
    PAttributeTypeFactory,
    ProjectAttributeFactory,
    ProjectStatusChoiceFactory,
    setup_models,
    ProjectAttributeTypeFactory,
    ProjectUserRoleChoiceFactory,
    fake
)
from coldfront.core.project.models import ProjectUserStatusChoice

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
        cls.project_user = cls.proj_allocation_user
        cls.nonproject_user = cls.nonproj_allocation_user
        # add pi_user and project_user to project_user

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

class ProjectDetailViewTest(ProjectViewTestBase):
    """tests for ProjectDetailView"""

    @classmethod
    def setUpTestData(cls):
        """Set up users and project for testing"""
        super(ProjectDetailViewTest, cls).setUpTestData()
        cls.projectattribute = ProjectAttributeFactory(value=36238,
                proj_attr_type=cls.projectattributetype, project=cls.project)
        cls.url = f'/project/{cls.project.pk}/'
        cls.no_allocation_project = ProjectFactory(title=fake.unique.project_title(),
                                pi=UserFactory(username=fake.unique.user_name()))

    def test_projectdetail_render(self):
        # test rendering for project with no allocation
        no_allocation_proj_url = f'/project/{self.no_allocation_project.pk}/'
        utils.test_user_can_access(self, self.admin_user, no_allocation_proj_url)

    def test_projectdetail_access(self):
        """Test project detail page access"""
        # logged-out user gets redirected, admin can access create page
        self.project_access_tstbase(self.url)
        # pi and projectuser can access
        utils.test_user_can_access(self, self.pi_user, self.url)
        utils.test_user_can_access(self, self.project_user, self.url)
        # user not belonging to project cannot access
        utils.test_user_cannot_access(self, self.nonproject_user, self.url)



    def test_projectdetail_permissions(self):
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

    def test_projectdetail_request_allocation_button_visibility(self):
        """Test visibility of project detail request allocation button to different projectuser levels"""
        utils.page_contains_for_user(self, self.admin_user, self.url, 'Request New Allocation') # admin can see request allocation button

        utils.page_contains_for_user(self, self.pi_user, self.url, 'Request New Allocation') # pi can see request allocation button

        response = utils.login_and_get_page(self.client, self.project_user, self.url)
        self.assertNotContains(response, 'Request New Allocation') # non-manager user cannot see request allocation button

    def test_projectdetail_edituser_button_visibility(self):
        """Test visibility of project detail edit button to different projectuser levels"""
        utils.page_contains_for_user(self, self.admin_user, self.url, 'fa-user-edit') # admin can see edit button

        utils.page_contains_for_user(self, self.pi_user, self.url, 'fa-user-edit') # pi can see edit button

        utils.page_does_not_contain_for_user(self, self.project_user, self.url, 'fa-user-edit') # non-manager user cannot see edit button


    def test_projectdetail_addattribute_button_visibility(self):
        """Test visibility of project detail add attribute button to different projectuser levels"""
        utils.page_contains_for_user(self, self.admin_user, self.url, 'Add Attribute') # admin can see add attribute button

        utils.page_does_not_contain_for_user(self, self.pi_user, self.url, 'Add Attribute') # pi cannot see add attribute button

        utils.page_does_not_contain_for_user(self, self.project_user, self.url, 'Add Attribute') # non-manager user cannot see add attribute button

    def test_projectdetail_addnotification_button_visibility(self):
        """Test visibility of project detail add notification button to different projectuser levels"""
        utils.page_contains_for_user(self, self.admin_user, self.url, 'Add Notification') # admin can see add notification button

        utils.page_does_not_contain_for_user(self, self.pi_user, self.url, 'Add Notification') # pi cannot see add notification button

        utils.page_does_not_contain_for_user(self, self.project_user, self.url, 'Add Notification') # non-manager user cannot see add notification button



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



class ProjectRemoveUsersViewTest(ProjectViewTestBase):
    """Tests for ProjectRemoveUsersView"""
    def setUp(self):
        """set up users and project for testing"""
        self.url = f'/project/{self.project.pk}/remove-users/'

    def test_projectremoveusersview_access(self):
        """test access to project remove users page"""
        self.project_access_tstbase(self.url)



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



class ProjectAddUsersSearchView(ProjectViewTestBase):
    """Tests for ProjectAddUsersSearchView"""
    def setUp(self):
        """set up users and project for testing"""
        self.url = f'/project/{self.project.pk}/add-users-search/'

    def test_projectadduserssearchview_access(self):
        """test access to project add users search page"""
        self.project_access_tstbase(self.url)



class ProjectUserDetailViewTest(ProjectViewTestBase):
    """Tests for ProjectUserDetailView"""
    def setUp(self):
        """set up users and project for testing"""
        self.url = f'/project/{self.project.pk}/user-detail/{self.project_user.pk}'

    def test_projectuserdetailview_access(self):
        """test access to project user detail page"""
        self.project_access_tstbase(self.url)
