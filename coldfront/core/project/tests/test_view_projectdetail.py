from django.urls import reverse

from coldfront.core.project.tests.test_views import ProjectViewTestBase
from coldfront.core.test_helpers import utils
from coldfront.core.test_helpers.factories import ProjectAttributeFactory
from coldfront.core.test_helpers.fasrc_factories import (
    OrganizationFactory,
    OrgRelationFactory,
    ProjectOrganizationFactory,
    UserAffiliationFactory,
)


class ProjectDetailViewTest(ProjectViewTestBase):
    """tests for ProjectDetailView"""

    @classmethod
    def setUpTestData(cls):
        """Set up users and project for testing"""
        super(ProjectDetailViewTest, cls).setUpTestData()
        cls.projectattribute = ProjectAttributeFactory(value=36238,
                proj_attr_type=cls.projectattributetype, project=cls.project)
        cls.url = f'/project/{cls.project.pk}/'

    ### Page access and permissions tests ###
    def test_projectdetail_access(self):
        """Test project detail page access. 
        pi and projectuser can access, nonproject user cannot access.
        """
        # logged-out user gets redirected, admin can access create page
        self.project_access_tstbase(self.url)
        utils.test_user_can_access(self, self.pi_user, self.url)
        utils.test_user_can_access(self, self.project_user, self.url)
        utils.test_user_cannot_access(self, self.nonproject_user, self.url)

    def test_projectdetail_permissions(self):
        """Test ProjectDetail page access permissions"""
        # admin and pi have is_allowed_to_update_project set to True
        response = utils.login_and_get_page(self.client, self.admin_user, self.url)
        self.assertEqual(response.context['is_allowed_to_update_project'], True)

        response = utils.login_and_get_page(self.client, self.pi_user, self.url)
        self.assertEqual(response.context['is_allowed_to_update_project'], True)

        # non-manager user has is_allowed_to_update_project set to False
        response = utils.login_and_get_page(self.client, self.project_user, self.url)
        self.assertEqual(response.context['is_allowed_to_update_project'], False)

    ### Permissions-related UI visibility tests ###
    def test_projectdetail_request_allocation_button_visibility(self):
        """Test ProjectDetail request allocation button visibility to different projectuser roles"""
        button_text = 'Request New Storage Allocation'
        # admin, pi, data manager can see request allocation button
        utils.page_contains_for_user(self, self.admin_user, self.url, button_text) 
        utils.page_contains_for_user(self, self.pi_user, self.url, button_text)
        utils.page_contains_for_user(self, self.proj_datamanager, self.url, button_text)
        # access manager, non-manager user cannot see request allocation button
        utils.page_does_not_contain_for_user(self, self.proj_accessmanager, self.url, button_text)
        utils.page_does_not_contain_for_user(self, self.project_user, self.url, button_text)

    def test_projectdetail_adduser_button_visibility(self):
        """Test ProjectDetail add user button visibility to different projectuser roles"""
        button_text = 'Add User'
        # admin, pi, accessmanager can see add user button
        utils.page_contains_for_user(self, self.admin_user, self.url, button_text)
        utils.page_contains_for_user(self, self.pi_user, self.url, button_text)
        utils.page_contains_for_user(self, self.proj_accessmanager, self.url, button_text)
        # storage manager, non-manager user cannot see add user button
        utils.page_does_not_contain_for_user(self, self.proj_datamanager, self.url, button_text)
        utils.page_does_not_contain_for_user(self, self.project_user, self.url, button_text)

    def test_projectdetail_edituser_button_visibility(self):
        """Test ProjectDetail edit button visibility to different projectuser roles"""
        utils.page_contains_for_user(self, self.admin_user, self.url, 'fa-user-edit') # admin can see edit button
        utils.page_contains_for_user(self, self.pi_user, self.url, 'fa-user-edit') # pi can see edit button
        # access manager, data manager, non-manager user cannot see edit button
        utils.page_does_not_contain_for_user(self, self.proj_accessmanager, self.url, 'fa-user-edit')
        utils.page_does_not_contain_for_user(self, self.proj_datamanager, self.url, 'fa-user-edit')
        utils.page_does_not_contain_for_user(self, self.project_user, self.url, 'fa-user-edit')

    def test_projectdetail_addattribute_button_visibility(self):
        """Test ProjectDetail add attribute button visibility to different projectuser roles"""
        search_text = 'Add Attribute'
        utils.page_contains_for_user(self, self.admin_user, self.url, search_text) # admin can see add attribute button
        # pi and non-manager cannot see add attribute button
        utils.page_does_not_contain_for_user(self, self.pi_user, self.url, search_text)
        utils.page_does_not_contain_for_user(self, self.project_user, self.url, search_text)

    def test_projectdetail_addnotification_button_visibility(self):
        """Test ProjectDetail add notification button visibility to different projectuser roles"""
        search_text = 'Add Notification'
        utils.page_contains_for_user(self, self.admin_user, self.url, search_text) # admin can see add notification button
        # pi, access manager, data manager, project user cannot see add notification button
        utils.page_does_not_contain_for_user(self, self.pi_user, self.url, search_text)
        utils.page_does_not_contain_for_user(self, self.proj_accessmanager, self.url, search_text)
        utils.page_does_not_contain_for_user(self, self.proj_datamanager, self.url, search_text)
        utils.page_does_not_contain_for_user(self, self.project_user, self.url, search_text)

    ### Data display tests ###
    def test_projectdetail_allocation_table(self):
        """Test ProjectDetail page storage allocation table"""
        # pi can see allocation in Allocations table
        soup = utils.login_and_get_soup(self.client, self.pi_user, self.url)
        allocations_table = soup.find('table', {'id': 'invoice_table'})
        self.assertIn("holylfs10/tier1", allocations_table.get_text())
        # project user belonging to allocation can see allocation
        soup = utils.login_and_get_soup(self.client, self.project_user, self.url)
        allocations_table = soup.find('table', {'id': 'invoice_table'})
        self.assertIn("holylfs10/tier1", allocations_table.get_text())
        # project user not belonging to allocation can see allocation
        soup = utils.login_and_get_soup(self.client, self.proj_nonallocationuser, self.url)
        allocations_table = soup.find('table', {'id': 'invoice_table'})
        self.assertIn("holylfs10/tier1", allocations_table.get_text())

    def test_projectdetail_department_displayed(self):
        """Test ProjectDetail shows the department of the project's lab, if any"""
        soup = utils.login_and_get_soup(self.client, self.pi_user, self.url)
        self.assertNotIn('Department:', soup.find('div', {'class': 'card-body'}).get_text())

        lab = OrganizationFactory(name=self.project.title, rank='lab', org_tree='Harvard')
        ProjectOrganizationFactory(project=self.project, organization=lab)
        dept = OrganizationFactory(
            name='Computational Chemistry',
            rank='department',
            org_tree='Research Computing Storage Billing',
        )
        OrgRelationFactory(parent=dept, child=lab)
        # parents outside the department org_tree are not shown
        other = OrganizationFactory(name='Not A Department', rank='department', org_tree='Harvard')
        OrgRelationFactory(parent=other, child=lab)

        soup = utils.login_and_get_soup(self.client, self.pi_user, self.url)
        card_text = soup.find('div', {'class': 'card-body'}).get_text()
        self.assertIn('Department: Computational Chemistry', card_text)
        self.assertNotIn('Not A Department', card_text)

    def test_projectdetail_department_link_only_if_viewable(self):
        """Test ProjectDetail links a department only for users who can view its detail page"""
        lab = OrganizationFactory(name=self.project.title, rank='lab', org_tree='Harvard')
        ProjectOrganizationFactory(project=self.project, organization=lab)
        dept = OrganizationFactory(
            name='Computational Chemistry',
            rank='department',
            org_tree='Research Computing Storage Billing',
        )
        OrgRelationFactory(parent=dept, child=lab)
        dept_url = reverse('department-detail', kwargs={'pk': dept.pk})

        # non-member sees the name without a link
        soup = utils.login_and_get_soup(self.client, self.pi_user, self.url)
        self.assertIn('Computational Chemistry', soup.find('div', {'class': 'card-body'}).get_text())
        self.assertIsNone(soup.find('a', href=dept_url))

        # department member and superuser see a link
        UserAffiliationFactory(user=self.pi_user, organization=dept)
        for user in (self.pi_user, self.admin_user):
            soup = utils.login_and_get_soup(self.client, user, self.url)
            self.assertIsNotNone(soup.find('a', href=dept_url))

    def test_projectdetail_allocation_history_table(self):
        """Test ProjectDetail page storage allocation history table"""
        # pi can see allocation in Allocations table
        soup = utils.login_and_get_soup(self.client, self.pi_user, self.url)
        allocations_table = soup.find('table', {'id': 'allocation_history'})
        self.assertIn("holylfs10/tier1", allocations_table.get_text())
        # project user belonging to allocation can see allocation
        soup = utils.login_and_get_soup(self.client, self.project_user, self.url)
        allocations_table = soup.find('table', {'id': 'allocation_history'})
        self.assertIn("holylfs10/tier1", allocations_table.get_text())
        # project user not belonging to allocation can see allocation
        soup = utils.login_and_get_soup(self.client, self.proj_nonallocationuser, self.url)
        allocations_table = soup.find('table', {'id': 'allocation_history'})
        self.assertIn("holylfs10/tier1", allocations_table.get_text())
