import datetime

from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from coldfront.core.project.tests.test_views import ProjectViewTestBase
from coldfront.core.test_helpers import utils
from coldfront.core.utils.common import import_from_settings
from coldfront.core.test_helpers.factories import (
    ProjectAttributeFactory,
    ProjectUserFactory,
    ProjectUserStatusChoiceFactory,
    UserFactory,
)
from coldfront.core.test_helpers.fasrc_factories import (
    OrganizationFactory,
    OrgRelationFactory,
    ProjectOrganizationFactory,
    UserAffiliationFactory,
)

ACCOUNT_TYPE_GROUPS = import_from_settings('ACCOUNT_TYPE_GROUPS')


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


class ProjectDetailViewDeactivatedUsersTest(ProjectViewTestBase):
    """Test how ProjectDetailView displays Active/Deactivated/Removed ProjectUsers.

    Deactivated means: still an AD group member, but the AD account is disabled -
    these should be shown (grayed out). Removed means: no longer a group member -
    these should not be shown at all.
    """

    @classmethod
    def setUpTestData(cls):
        super(ProjectDetailViewDeactivatedUsersTest, cls).setUpTestData()
        cls.url = f'/project/{cls.project.pk}/'

        cls.deactivated_user = UserFactory(username='deactivated_user')
        cls.deactivated_projectuser = ProjectUserFactory(
            user=cls.deactivated_user, project=cls.project,
            status=ProjectUserStatusChoiceFactory(name='Deactivated'),
        )
        cls.removed_user = UserFactory(username='removed_user')
        cls.removed_projectuser = ProjectUserFactory(
            user=cls.removed_user, project=cls.project,
            status=ProjectUserStatusChoiceFactory(name='Removed'),
        )

    def test_deactivated_user_shown_removed_user_not_shown(self):
        response = utils.login_and_get_page(self.client, self.pi_user, self.url)
        project_user_usernames = [pu.user.username for pu in response.context['project_users']]
        self.assertIn(self.deactivated_user.username, project_user_usernames)
        self.assertNotIn(self.removed_user.username, project_user_usernames)

    def test_deactivated_user_row_is_grayed_out_with_badge(self):
        soup = utils.login_and_get_soup(self.client, self.pi_user, self.url)
        table = soup.find('table', {'id': 'projectuser_table'})
        row = next(
            tr for tr in table.find_all('tr')
            if self.deactivated_user.username in tr.get_text()
        )
        self.assertIn('text-muted', row.get('class', []))
        self.assertIn('Disabled', row.get_text())

    def test_deactivated_user_row_has_no_edit_link(self):
        """No link to the projectuser edit page is shown for a Deactivated
        user, since that page is unreachable for them."""
        soup = utils.login_and_get_soup(self.client, self.pi_user, self.url)
        table = soup.find('table', {'id': 'projectuser_table'})
        row = next(
            tr for tr in table.find_all('tr')
            if self.deactivated_user.username in tr.get_text()
        )
        self.assertNotIn('fa-user-edit', str(row))

    def test_removed_user_row_absent_from_table(self):
        soup = utils.login_and_get_soup(self.client, self.pi_user, self.url)
        table = soup.find('table', {'id': 'projectuser_table'})
        self.assertNotIn(self.removed_user.username, table.get_text())

    def test_mailto_excludes_deactivated_user_email(self):
        response = utils.login_and_get_page(self.client, self.pi_user, self.url)
        self.assertNotIn(self.deactivated_user.email, response.context['mailto'])
        self.assertIn(self.pi_user.email, response.context['mailto'])


class ProjectDetailViewAccountTypeBadgesTest(ProjectViewTestBase):
    """Test that ProjectDetailView badges users by their ACCOUNT_TYPE_GROUPS presets."""

    @classmethod
    def setUpTestData(cls):
        super(ProjectDetailViewAccountTypeBadgesTest, cls).setUpTestData()
        cls.url = f'/project/{cls.project.pk}/'
        cls.active_status = ProjectUserStatusChoiceFactory(name='Active')
        # one project user per account-type group
        cls.group_users = {}
        for group_name in ACCOUNT_TYPE_GROUPS:
            cls.group_users[group_name] = cls._add_member(f'{group_name}_user', [group_name])

    @classmethod
    def _add_member(cls, username, group_names):
        user = UserFactory(username=username)
        for group_name in group_names:
            user.groups.add(Group.objects.get_or_create(name=group_name)[0])
        ProjectUserFactory(user=user, project=cls.project, status=cls.active_status)
        return user

    def _get_cells(self, soup, username):
        """Return the (username, name) cells of the user's projectuser_table row"""
        table = soup.find('table', {'id': 'projectuser_table'})
        row = next(tr for tr in table.find_all('tr') if username in tr.get_text())
        cells = row.find_all('td')
        return cells[0], cells[1]

    def _badges(self, cell):
        return [(b.get_text(strip=True), b['class']) for b in cell.find_all('span', class_='badge')]

    def test_each_group_gets_its_preset_badge_after_username(self):
        soup = utils.login_and_get_soup(self.client, self.pi_user, self.url)
        for group_name, preset in ACCOUNT_TYPE_GROUPS.items():
            with self.subTest(group=group_name):
                username_cell, name_cell = self._get_cells(soup, self.group_users[group_name].username)
                self.assertEqual(self._badges(username_cell), [(preset['label'], ['badge', preset['badge_class']])])
                self.assertEqual(self._badges(name_cell), [])

    def test_vendor_badge_supersedes_external(self):
        user = self._add_member('multi_type_user', ['external', 'vendor'])
        soup = utils.login_and_get_soup(self.client, self.pi_user, self.url)
        username_cell, _ = self._get_cells(soup, user.username)
        vendor = ACCOUNT_TYPE_GROUPS['vendor']
        self.assertEqual(self._badges(username_cell), [(vendor['label'], ['badge', vendor['badge_class']])])

    def test_vendor_badge_is_orange(self):
        soup = utils.login_and_get_soup(self.client, self.pi_user, self.url)
        username_cell, _ = self._get_cells(soup, self.group_users['vendor'].username)
        self.assertIsNotNone(username_cell.find('span', class_='badge-vendor'))

    def test_internal_user_has_no_badge(self):
        soup = utils.login_and_get_soup(self.client, self.pi_user, self.url)
        username_cell, name_cell = self._get_cells(soup, self.pi_user.username)
        self.assertEqual(self._badges(username_cell), [])
        self.assertEqual(self._badges(name_cell), [])


class ProjectDetailViewExpirationBadgeTest(ProjectViewTestBase):
    """Test that ProjectDetailView badges users whose accounts expire within 30 days."""

    @classmethod
    def setUpTestData(cls):
        super(ProjectDetailViewExpirationBadgeTest, cls).setUpTestData()
        cls.url = f'/project/{cls.project.pk}/'
        active_status = ProjectUserStatusChoiceFactory(name='Active')
        cls.expiring_user = UserFactory(username='expiring_user')
        cls.expiring_user.groups.add(Group.objects.get_or_create(name='external')[0])
        ProjectUserFactory(user=cls.expiring_user, project=cls.project, status=active_status)

    def _set_expiration_days_out(self, days):
        self.expiring_user.expiration = timezone.now() + datetime.timedelta(days=days)
        self.expiring_user.save()

    def _badges(self):
        soup = utils.login_and_get_soup(self.client, self.pi_user, self.url)
        table = soup.find('table', {'id': 'projectuser_table'})
        row = next(tr for tr in table.find_all('tr') if 'expiring_user' in tr.get_text())
        return [badge.get_text(strip=True) for badge in row.find_all('td')[0].find_all('span', class_='badge')]

    def test_badge_shown_after_external_badge_when_expiring_within_30_days(self):
        self._set_expiration_days_out(12)
        days_left = (timezone.localdate(self.expiring_user.expiration) - timezone.localdate()).days
        self.assertEqual(self._badges(), ['External', f'exp. {days_left} days'])

    def test_badge_is_red(self):
        self._set_expiration_days_out(12)
        soup = utils.login_and_get_soup(self.client, self.pi_user, self.url)
        self.assertIsNotNone(soup.find('span', class_='badge-danger', string=lambda s: s and s.startswith('exp.')))

    def test_badge_uses_singular_day(self):
        self.expiring_user.expiration = timezone.make_aware(
            datetime.datetime.combine(timezone.localdate() + datetime.timedelta(days=1), datetime.time(12)))
        self.expiring_user.save()
        self.assertIn('exp. 1 day', self._badges())

    def test_no_badge_at_30_days_or_more(self):
        self.expiring_user.expiration = timezone.make_aware(
            datetime.datetime.combine(timezone.localdate() + datetime.timedelta(days=30), datetime.time(12)))
        self.expiring_user.save()
        self.assertEqual(self._badges(), ['External'])

    def test_no_badge_without_expiration(self):
        self.expiring_user.expiration = None
        self.expiring_user.save()
        self.assertEqual(self._badges(), ['External'])

    def test_no_badge_when_already_expired(self):
        self._set_expiration_days_out(-3)
        self.assertEqual(self._badges(), ['External'])
