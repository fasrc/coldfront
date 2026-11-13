import datetime

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from coldfront.core.test_helpers.factories import (
    ProjectFactory,
    ProjectStatusChoiceFactory,
    UserFactory,
)

from coldfront.core.test_helpers import utils
from coldfront.core.utils.common import import_from_settings
from coldfront.core.user.models import UserProfile
from coldfront.core.user.tasks import sync_userprofile_is_pi

ACCOUNT_TYPE_GROUPS = import_from_settings('ACCOUNT_TYPE_GROUPS')

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

    def test_each_account_type_group_shows_its_label(self):
        for group_name, preset in ACCOUNT_TYPE_GROUPS.items():
            with self.subTest(group=group_name):
                user = UserFactory(username=f'{group_name}_user')
                user.groups.add(Group.objects.get_or_create(name=group_name)[0])
                self.assertEqual(self._get_status_cell(user).get_text(strip=True), preset['label'])

    def test_vendor_supersedes_external(self):
        user = UserFactory(username='multi_external_user')
        for group_name in ('external', 'vendor'):
            user.groups.add(Group.objects.get_or_create(name=group_name)[0])
        self.assertEqual(
            self._get_status_cell(user).get_text(strip=True), ACCOUNT_TYPE_GROUPS['vendor']['label']
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


class TestSyncUserProfileIsPi(TestCase):
    """Tests for the sync_userprofile_is_pi task."""

    def make_user(self, username, is_pi):
        user = UserFactory(username=username)
        user.userprofile.is_pi = is_pi
        user.userprofile.save()
        return user

    def assert_is_pi(self, user, expected):
        user.userprofile.refresh_from_db()
        self.assertEqual(user.userprofile.is_pi, expected)

    def test_sync_userprofile_is_pi_sets_profiles_to_match_project_pis(self):
        new_pi = self.make_user('new_pi', is_pi=False)
        active_pi = self.make_user('active_pi', is_pi=False)
        archived_pi = self.make_user('archived_pi', is_pi=True)
        mixed_pi = self.make_user('mixed_pi', is_pi=True)
        former_pi = self.make_user('former_pi', is_pi=True)
        non_pi = self.make_user('non_pi', is_pi=False)

        ProjectFactory(pi=new_pi, status=ProjectStatusChoiceFactory(name='New'))
        ProjectFactory(pi=active_pi, status=ProjectStatusChoiceFactory(name='Active'))
        ProjectFactory(pi=archived_pi, status=ProjectStatusChoiceFactory(name='Archived'))
        ProjectFactory(pi=mixed_pi, status=ProjectStatusChoiceFactory(name='Archived'))
        ProjectFactory(pi=mixed_pi, status=ProjectStatusChoiceFactory(name='Active'))

        promoted, demoted = sync_userprofile_is_pi()

        self.assertEqual((promoted, demoted), (2, 2))
        self.assert_is_pi(new_pi, True)
        self.assert_is_pi(active_pi, True)
        self.assert_is_pi(archived_pi, False)
        self.assert_is_pi(mixed_pi, True)
        self.assert_is_pi(former_pi, False)
        self.assert_is_pi(non_pi, False)

    def test_sync_userprofile_is_pi_already_synced_is_noop(self):
        pi = self.make_user('pi', is_pi=True)
        self.make_user('non_pi', is_pi=False)
        ProjectFactory(pi=pi, status=ProjectStatusChoiceFactory(name='Active'))

        self.assertEqual(sync_userprofile_is_pi(), (0, 0))
        self.assert_is_pi(pi, True)
