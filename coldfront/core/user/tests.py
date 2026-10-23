from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from coldfront.core.test_helpers.factories import (
    UserFactory,
)

from coldfront.core.test_helpers import utils
from coldfront.core.user.models import UserProfile

class TestUserProfile(TestCase):
    class Data:
        """Collection of test data, separated for readability"""

        def __init__(self):
            user = UserFactory(username='submitter')

            self.initial_fields = {
                'user': user,
                'is_pi': True,
                'id': user.id
            }
            
            self.unsaved_object = UserProfile(**self.initial_fields)
    
    def setUp(self):
        self.data = self.Data()

    def test_fields_generic(self):
        profile_obj = self.data.unsaved_object
        profile_obj.save()

        self.assertEqual(1, len(UserProfile.objects.all()))

        retrieved_profile = UserProfile.objects.get(pk=profile_obj.pk)

        for item in self.data.initial_fields.items():
            (field, initial_value) = item
            with self.subTest(item=item):
                saved_value = getattr(retrieved_profile, field)
                self.assertEqual(initial_value, saved_value)
        self.assertEqual(profile_obj, retrieved_profile)

    def test_user_on_delete(self):
        profile_obj = self.data.unsaved_object
        profile_obj.save()

        self.assertEqual(1, len(UserProfile.objects.all()))

        profile_obj.user.delete()

        # expecting CASCADE
        with self.assertRaises(UserProfile.DoesNotExist):
            UserProfile.objects.get(pk=profile_obj.pk)
        self.assertEqual(0, len(UserProfile.objects.all()))

class TestUserProfileExternalStatus(TestCase):
    """Test that the user profile page shows external/vendor status."""

    def _get_status_cell(self, user):
        soup = utils.login_and_get_soup(self.client, user, reverse('user-profile'))
        header = soup.find('th', string='External Status:')
        return header.find_next_sibling('td')

    def test_external_user_shows_external(self):
        user = UserFactory(username='external_user')
        user.groups.add(Group.objects.get_or_create(name='external')[0])
        self.assertEqual(self._get_status_cell(user).get_text(strip=True), 'External')

    def test_vendor_user_shows_vendor(self):
        user = UserFactory(username='vendor_user')
        user.groups.add(Group.objects.get_or_create(name='vendor')[0])
        self.assertEqual(self._get_status_cell(user).get_text(strip=True), 'Vendor')

    def test_internal_user_shows_no(self):
        user = UserFactory(username='internal_user')
        self.assertEqual(self._get_status_cell(user).get_text(strip=True), 'No')
