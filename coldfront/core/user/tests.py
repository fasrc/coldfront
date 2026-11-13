import datetime

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from coldfront.core.test_helpers.factories import (
    UserFactory,
)

from coldfront.core.test_helpers import utils
from coldfront.core.utils.common import import_from_settings
from coldfront.core.user.models import UserProfile

EXTERNAL_USER_GROUPS = import_from_settings('EXTERNAL_USER_GROUPS', ['external', 'vendor'])

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
    """Test that the user profile page shows which external groups a user is in."""

    def _get_status_cell(self, user):
        soup = utils.login_and_get_soup(self.client, user, reverse('user-profile'))
        header = soup.find('th', string='External Status:')
        return header.find_next_sibling('td')

    def test_each_external_group_shows_its_name(self):
        for group_name in EXTERNAL_USER_GROUPS:
            with self.subTest(group=group_name):
                user = UserFactory(username=f'{group_name}_user')
                user.groups.add(Group.objects.get_or_create(name=group_name)[0])
                self.assertEqual(self._get_status_cell(user).get_text(strip=True), group_name.capitalize())

    def test_user_in_several_external_groups_shows_all(self):
        user = UserFactory(username='multi_external_user')
        for group_name in EXTERNAL_USER_GROUPS:
            user.groups.add(Group.objects.get_or_create(name=group_name)[0])
        self.assertEqual(
            self._get_status_cell(user).get_text(strip=True),
            ', '.join(group_name.capitalize() for group_name in EXTERNAL_USER_GROUPS),
        )

    def test_internal_user_shows_no(self):
        user = UserFactory(username='internal_user')
        self.assertEqual(self._get_status_cell(user).get_text(strip=True), 'No')


class TestUserProfileExpiration(TestCase):
    """Test that the user profile page shows the account expiration when set."""

    def _get_soup(self, user):
        return utils.login_and_get_soup(self.client, user, reverse('user-profile'))

    def test_expiration_shown_when_set(self):
        user = UserFactory(username='expiring_user')
        user.expiration = timezone.now() + datetime.timedelta(days=30)
        user.save()
        header = self._get_soup(user).find('th', string='Account Expiration:')
        self.assertIsNotNone(header)
        self.assertEqual(
            header.find_next_sibling('td').get_text(strip=True),
            timezone.localdate(user.expiration).isoformat(),
        )

    def test_expiration_hidden_when_unset(self):
        user = UserFactory(username='nonexpiring_user')
        user.expiration = None
        user.save()
        self.assertIsNone(self._get_soup(user).find('th', string='Account Expiration:'))
