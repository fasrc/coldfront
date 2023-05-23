import logging

from django.db.models import Count
from django.test import TestCase
from django.urls import reverse

from coldfront.core.test_helpers import utils
from coldfront.core.allocation.models import (Allocation,
                                AllocationUserNote,
                                AllocationAttribute,
                                AllocationChangeRequest)
from coldfront.core.test_helpers.factories import (fake,
                                setup_models,
                                ResourceFactory,
                                UserFactory,
                                ProjectFactory,
                                AllocationFactory,
                                AllocationChangeRequestFactory
                                )


logging.disable(logging.CRITICAL)

UTIL_FIXTURES = [
        "coldfront/core/test_helpers/test_data/test_fixtures/ifx.json",
]


class AllocationQC(TestCase):
    def check_resource_quotas(self):
        zero_quotas = AllocationAttribute.objects.filter(
                            allocation_attribute_type__in=[1,5], value=0)
        self.assertEqual(zero_quotas.count(), 0)

    def check_resource_counts(self):
        over_one = Allocation.objects.annotate(resource_count=Count('resources')).filter(resource_count__gt=1)
        self.assertEqual(over_one.count(), 0)




class AllocationViewBaseTest(TestCase):
    """Base class for allocation view tests.
    """
    fixtures = UTIL_FIXTURES

    @classmethod
    def setUpTestData(cls):
        """Test Data setup for all allocation view tests.
        """
        setup_models(cls)


    def allocation_access_tstbase(self, url):
        """Test basic access control for views. For all views:
        - if not logged in, redirect to login page
        - if logged in as admin, can access page
        """
        utils.test_logged_out_redirect_to_login(self, url) # If not logged in, can't see page; redirect to login page.
        utils.test_user_can_access(self, self.admin_user, url) # after login, pi and admin can access create page



class AllocationListViewTest(AllocationViewBaseTest):


    @classmethod
    def setUpTestData(cls):
        """Set up users and project for testing"""
        super(AllocationListViewTest, cls).setUpTestData()
        cls.additional_allocations = [
                AllocationFactory(
                    project=ProjectFactory(
                        title=fake.unique.project_title(),
                        pi=UserFactory(username=fake.unique.username())
                        )
                    )
            for i in list(range(100))
                             ]
        for allocation in cls.additional_allocations:
            allocation.resources.add(ResourceFactory(name='holylfs09/tier1', id=2))
        cls.nonproj_nonallocation_user = UserFactory(username='rdrake',
                    is_staff=False, is_superuser=False)

    def test_allocation_list_access_admin(self):
        """Confirm that AllocationList access control works for admin
        """
        self.allocation_access_tstbase('/allocation/')

        # confirm that show_all_allocations=on enables admin to view all allocations
        response = self.client.get("/allocation/?show_all_allocations=on")
        self.assertEqual(len(response.context['item_list']), 25)

    def test_allocation_list_access_pi(self):
        """Confirm that AllocationList access control works for pi
        When show_all_allocations=on, pi still sees only allocations belonging
        to the projects they are pi for.
        """
        # confirm that show_all_allocations=on enables admin to view all allocations
        self.client.force_login(self.pi_user,
                    backend="django.contrib.auth.backends.ModelBackend")
        response = self.client.get("/allocation/?show_all_allocations=on")
        self.assertEqual(len(response.context['item_list']), 1)

    def test_allocation_list_access_user(self):
        """Confirm that AllocationList access control works for non-pi users
        When show_all_allocations=on, users see only the allocations they
        are AllocationUsers of.
        """
        # confirm that show_all_allocations=on is accessible to non-admin but
        # contains only the user's allocations
        self.client.force_login(self.proj_allocation_user, backend="django.contrib.auth.backends.ModelBackend")
        response = self.client.get("/allocation/")
        self.assertEqual(len(response.context['item_list']), 1)
        response = self.client.get("/allocation/?show_all_allocations=on")
        self.assertEqual(len(response.context['item_list']), 1)

        # allocation user not belonging to project can see allocation
        self.client.force_login(self.nonproj_allocation_user, backend="django.contrib.auth.backends.ModelBackend")
        response = self.client.get("/allocation/")
        self.assertEqual(len(response.context['item_list']), 1)
        response = self.client.get("/allocation/?show_all_allocations=on")
        self.assertEqual(len(response.context['item_list']), 1)

        # nonallocation user belonging to project can't see allocation
        self.client.force_login(self.nonproj_nonallocation_user, backend="django.contrib.auth.backends.ModelBackend")
        response = self.client.get("/allocation/?show_all_allocations=on")
        self.assertEqual(len(response.context['item_list']), 0)

        # nonallocation user belonging to project can't see allocation
        self.client.force_login(self.proj_nonallocation_user, backend="django.contrib.auth.backends.ModelBackend")
        response = self.client.get("/allocation/?show_all_allocations=on")
        self.assertEqual(len(response.context['item_list']), 0)

    def test_allocation_list_search_admin(self):
        """Confirm that AllocationList search works for admin
        """
        self.client.force_login(self.admin_user, backend="django.contrib.auth.backends.ModelBackend")
        base_url = '/allocation/?show_all_allocations=on'
        response = self.client.get(base_url + f'&resource_name={self.proj_allocation.resources.first().pk}')
        self.assertEqual(len(response.context['item_list']), 1)


class AllocationChangeDetailViewTest(AllocationViewBaseTest):

    def setUp(self):
        """create an AllocationChangeRequest to test
        """
        self.client.force_login(self.admin_user, backend="django.contrib.auth.backends.ModelBackend")
        AllocationChangeRequestFactory(id=2, allocation=self.proj_allocation)

    def test_allocationchangedetailview_access(self):
        response = self.client.get(reverse('allocation-change-detail', kwargs={'pk':2}))
        self.assertEqual(response.status_code, 200)

    def test_allocationchangedetailview_post_deny(self):
        param = {'action': 'deny'}
        response = self.client.post(reverse('allocation-change-detail', kwargs={'pk':2}),
        param, follow=True)
        self.assertEqual(response.status_code, 200)
        alloc_change_req = AllocationChangeRequest.objects.get(pk=2)
        self.assertEqual(alloc_change_req.status_id, 3)

    def test_allocationchangedetailview_post_approve(self):
        # with nothing changed, should get error message of "You must make a change to the allocation."
        param = {'action': 'approve'}
        response = self.client.post(reverse('allocation-change-detail', kwargs={'pk':2}),
        param, follow=True)
        self.assertEqual(response.status_code, 200)
        messages = list(response.context['messages'])
        self.assertEqual(str(messages[0]), "You must make a change to the allocation.")
        # alloc_change_req = AllocationChangeRequest.objects.get(pk=2)
        # self.assertEqual(alloc_change_req.status_id, 2)


class AllocationChangeViewTest(AllocationViewBaseTest):

    def setUp(self):
        self.client.force_login(self.admin_user,
                backend="django.contrib.auth.backends.ModelBackend")

    def test_allocationchangeview_access(self):
        """
        """
        kwargs={'pk':1, }
        response = self.client.get('/allocation/1/change-request', kwargs=kwargs)
        self.assertEqual(response.status_code, 200) #Admin can access


class AllocationDetailViewTest(AllocationViewBaseTest):

    def setUp(self):
        self.url = f'/allocation/{self.proj_allocation.pk}/'

    def test_allocation_detail_access(self):
        self.allocation_access_tstbase(self.url)
        utils.test_user_can_access(self, self.pi_user, self.url) #Manager can access, even if not an allocation user
        utils.test_user_cannot_access(self, self.proj_nonallocation_user, self.url) #nonallocation user can't access
        # check access for allocation user with "Removed" status

    def test_allocation_detail_template_value_render(self):
        """Confirm that quota_tb and usage_tb are correctly rendered in the
        generated AllocationDetailView
        """
        self.client.force_login(self.admin_user,
                backend="django.contrib.auth.backends.ModelBackend")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        # check that allocation_quota_tb has value
        self.assertEqual(response.context['allocation_quota_bytes'], 109951162777600)
        # check that allocation_usage_tb has value
        self.assertEqual(response.context['allocation_usage_bytes'], 10995116277760)


    def test_allocationdetail_requestchange_button(self):
        """Test visibility of the "Request Change" button for different user types
        """
        # admin
        utils.page_contains_for_user(self, self.admin_user, self.url, 'Request Change')
        # pi
        utils.page_contains_for_user(self, self.pi_user, self.url, 'Request Change')
        # allocation user
        utils.page_does_not_contain_for_user(self, self.proj_allocation_user, self.url, 'Request Change')


    def test_allocationattribute_button_visibility(self):
        """Test visibility of the "Add Attribute" button for different user types
        """
        # admin
        utils.page_contains_for_user(self, self.admin_user, self.url, 'Add Allocation Attribute')
        utils.page_contains_for_user(self, self.admin_user, self.url, 'Delete Allocation Attribute')
        # pi
        utils.page_does_not_contain_for_user(self, self.pi_user, self.url, 'Add Allocation Attribute')
        utils.page_does_not_contain_for_user(self, self.pi_user, self.url, 'Delete Allocation Attribute')
        # allocation user
        utils.page_does_not_contain_for_user(self, self.proj_allocation_user, self.url, 'Add Allocation Attribute')
        utils.page_does_not_contain_for_user(self, self.proj_allocation_user, self.url, 'Delete Allocation Attribute')

    def test_allocationuser_button_visibility(self):
        """Test visibility of the "Add/Remove Users" buttons for different user types
        """
        # admin
        # utils.page_contains_for_user(self, self.admin_user, self.url, 'Add Users')
        # utils.page_contains_for_user(self, self.admin_user, self.url, 'Remove Users')
        # we're removing these buttons for everybody, to avoid confusion re: procedure for user addition/removal
        utils.page_does_not_contain_for_user(self, self.admin_user, self.url, 'Add Users')
        utils.page_does_not_contain_for_user(self, self.admin_user, self.url, 'Remove Users')
        # pi
        utils.page_does_not_contain_for_user(self, self.pi_user, self.url, 'Add Users')
        utils.page_does_not_contain_for_user(self, self.pi_user, self.url, 'Remove Users')
        # allocation user
        utils.page_does_not_contain_for_user(self, self.proj_allocation_user, self.url, 'Add Users')
        utils.page_does_not_contain_for_user(self, self.proj_allocation_user, self.url, 'Remove Users')


class AllocationCreateViewTest(AllocationViewBaseTest):
    """Tests for the AllocationCreateView"""
    def setUp(self):
        self.url = f'/allocation/project/{self.project.pk}/create' #url for AllocationCreateView

    def test_allocationcreateview_access(self):
        """Test access to the AllocationCreateView"""
        self.allocation_access_tstbase(self.url)
        # add test to determine if PI can access this view
        utils.test_user_cannot_access(self, self.proj_nonallocation_user, self.url)



class AllocationAddUsersViewTest(AllocationViewBaseTest):
    """Tests for the AllocationAddUsersView"""
    def setUp(self):
        self.url = f'/allocation/{self.proj_allocation.pk}/add-users'

    def test_allocationaddusersview_access(self):
        self.allocation_access_tstbase(self.url)


class AllocationRemoveUsersViewTest(AllocationViewBaseTest):
    """Tests for the AllocationRemoveUsersView"""
    def setUp(self):
        self.url = f'/allocation/{self.proj_allocation.pk}/remove-users'

    def test_allocationremoveusersview_access(self):
        self.allocation_access_tstbase(self.url)


class AllocationRequestListViewTest(AllocationViewBaseTest):
    """Tests for the AllocationRequestListView"""
    def setUp(self):
        self.url = '/allocation/request-list'

    def test_allocationrequestlistview_access(self):
        self.allocation_access_tstbase(self.url)



class AllocationChangeListViewTest(AllocationViewBaseTest):
    """Tests for the AllocationChangeListView"""
    def setUp(self):
        self.url = '/allocation/change-list'

    def test_allocationchangelistview_access(self):
        self.allocation_access_tstbase(self.url)



class AllocationNoteCreateViewTest(AllocationViewBaseTest):
    """Tests for the AllocationNoteCreateView"""
    def setUp(self):
        self.url = f'/allocation/{self.proj_allocation.pk}/allocationnote/add'

    def test_allocationnotecreateview_access(self):
        self.allocation_access_tstbase(self.url)



class AllocationNoteUpdateViewTest(AllocationViewBaseTest):
    """Tests for the AllocationNoteUpdateView"""
    def setUp(self):
        self.proj_allocation_note = AllocationUserNote.objects.create(
            allocation=self.proj_allocation,
            note='test note',
            author=self.admin_user,
            )
        self.url = f'/allocation/allocation-note/{self.proj_allocation_note.pk}/update'

    def test_allocationnoteupdateview_access(self):
        self.allocation_access_tstbase(self.url)
