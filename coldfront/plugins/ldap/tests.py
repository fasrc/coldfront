from datetime import datetime
from unittest.mock import patch
import pandas as pd

from ldap3.core.exceptions import LDAPSocketOpenError
from ldap3.core.timezone import OffsetTzInfo
from django.core import mail
from django.test import TestCase, override_settings, tag
from django.contrib.auth import get_user_model
from django_q.models import Schedule

from coldfront.core.project.exceptions import ProjectUserDeactivatedError, ProjectUserStatusChangeError
from coldfront.core.project.models import ProjectUser
from coldfront.plugins.ldap.projectuser_sync import apply_ad_intent as real_apply_ad_intent
from coldfront.plugins.ldap.tasks import apply_projectuser_ad_change
from coldfront.plugins.ldap.utils import (
    LDAPConn,
    LDAPUserDeactivatedError,
    LDAPUserRemovalError,
    GroupUserCollection,
    add_new_projects,
    collect_update_project_status_membership,
    format_template_assertions,
)
from coldfront.core.test_helpers.factories import (
    setup_models,
    ProjectFactory,
    ProjectStatusChoiceFactory,
    ProjectUserFactory,
    ProjectUserRoleChoiceFactory,
    ProjectUserStatusChoiceFactory,
    AllocationUserStatusChoiceFactory,
    UserFactory,
)


UTIL_FIXTURES = [
    "coldfront/core/test_helpers/test_data/test_fixtures/ifx.json",
]

class UtilFunctionTests(TestCase):

    def test_format_template_assertions_one_kv(self):
        """Format attr_search_dict with one key-value pair into correct filter_template input
        """
        test_data = {'company': 'FAS'}
        desired_output = '(company=FAS)'
        output = format_template_assertions(test_data)
        self.assertEqual(output, desired_output)

    def test_format_template_assertions_multi_kv(self):
        """Format attr_search_dict with multiple key-value pairs into correct filter_template input
        """
        test_data = {'cn': 'Bob Smith', 'company': 'FAS'}
        desired_output = '(&(cn=Bob Smith)(company=FAS))'
        output = format_template_assertions(test_data)
        self.assertEqual(output, desired_output)

    def test_format_template_assertions_list_value(self):
        """Format attr_search_dict with list value into correct filter_template input
        """
        test_data = {'cn': ['Bob Smith', 'Jane Doe'], 'company': 'FAS'}
        desired_output = '(&(|(cn=Bob Smith)(cn=Jane Doe))(company=FAS))'
        output = format_template_assertions(test_data)
        self.assertEqual(output, desired_output)


class LDAPConnTest(TestCase):
    """tests for LDAPConn class"""

    @tag('net')
    def setUp(self):
        self.ldap_conn = LDAPConn()

    @tag('net')
    def test_search_group_one_kv(self):
        """Be able to return correct group with the variables given
        """
        attr_search_dict = {'sAMAccountName': 'rc_test_lab'}
        results = self.ldap_conn.search_groups(attr_search_dict)
        self.assertEqual(len(results), 1)

    @tag('net')
    def test_search_user_one_kv(self):
        """Be able to return correct user with the variables given
        """
        attr_search_dict = {'sAMAccountName': 'atestaccount'}
        results = self.ldap_conn.search_users(attr_search_dict)
        self.assertEqual(len(results), 1)

    @tag('net')
    def test_search_user_membership(self):
        """Be able to return correct user with the variables given
        """
        attr_search_dict = {'memberOf': 'CN=rc_test_lab,OU=RC,OU=Domain Groups,DC=rc,DC=domain'}
        results = self.ldap_conn.search_users(attr_search_dict)
        self.assertEqual(len(results), 6)

    @tag('net')
    def test_return_group_members_manager(self):
        samaccountname = 'rc_test_lab'
        result = self.ldap_conn.return_group_members_manager(samaccountname)
        self.assertEqual(result, 'no ADUser manager found')

        samaccountname = 'cepr_test_group'
        members, manager = self.ldap_conn.return_group_members_manager(samaccountname)
        self.assertEqual(len(members), 1)


class GroupUserCollectionTests(TestCase):
    """Tests for GroupUserCollection class"""
    fixtures = UTIL_FIXTURES


    def setUp(self):
        setup_models(self)

        group_name = 'bortkiewicz_lab'
        self.currentuser_accountExpires = [datetime(9999, 12, 31, 23, 59, 59, 999999, tzinfo=OffsetTzInfo(offset=0, name='UTC'))]
        self.expireduser_accountExpires = [datetime(1601, 12, 31, 23, 59, 59, 999999, tzinfo=OffsetTzInfo(offset=0, name='UTC'))]
        ad_users = [
            {
                'sAMAccountName': ['ljbortkiewicz'],
                'department': ['Statistics and Probability'],
                'userAccountControl': [512],
                'accountExpires': self.currentuser_accountExpires,
                'gidNumber': [5001],
            },
            {
                'sAMAccountName': ['sdpoisson'],
                'department': ['Statistics and Probability'],
                'userAccountControl': [512],
                'accountExpires': self.currentuser_accountExpires,
                'gidNumber': [5001],
            },
            {
                'sAMAccountName': ['snewcomb'],
                'department': ['Statistics and Probability'],
                'userAccountControl': [512],
                'accountExpires': self.currentuser_accountExpires,
                'gidNumber': [9999],
            },
        ]
        pi = {
            'sAMAccountName': ['ljbortkiewicz'],
            'department': ['Statistics and Probability'],
            'userAccountControl': [512],
            'memberOf': ['CD=non_faculty_pi'],
            'accountExpires': self.currentuser_accountExpires,
        }
        self.guc = (GroupUserCollection(group_name, ad_users, pi))

    def disable_pi(self):
        self.guc.pi['userAccountControl'] = [514]
        self.guc.members[0]['userAccountControl'] = [514]

    def test_pi_is_active(self):
        self.assertEqual(self.guc.pi_is_active, True)

    def test_current_ad_users(self):
        self.assertEqual(len(self.guc.current_ad_users), 3)

    def test_current_ad_usernames_none_disabled(self):
        self.assertEqual(
            self.guc.current_ad_usernames, {'ljbortkiewicz', 'sdpoisson', 'snewcomb'}
        )

    def test_disabled_ad_usernames_none_disabled(self):
        self.assertEqual(self.guc.disabled_ad_usernames, set())

    def test_disabled_ad_usernames_with_disabled_member(self):
        """a member whose AD account is disabled shows up as disabled, not current"""
        self.guc.members[1]['userAccountControl'] = [514]
        self.assertEqual(self.guc.disabled_ad_usernames, {'sdpoisson'})
        self.assertEqual(self.guc.current_ad_usernames, {'ljbortkiewicz', 'snewcomb'})

    def test_pi_disabled(self):
        self.disable_pi()
        self.assertEqual(self.guc.pi_is_active, False)

    def test_primary_member_usernames_no_group_gid(self):
        """group_gid_number unset -> no members are ever identified as primary"""
        self.assertEqual(self.guc.primary_member_usernames, set())

    def test_primary_member_usernames_matching(self):
        self.guc.group_gid_number = 5001
        self.assertEqual(self.guc.primary_member_usernames, {'ljbortkiewicz', 'sdpoisson'})

    def test_primary_member_usernames_member_missing_gid(self):
        """a member with no gidNumber attribute at all is never primary, and
        doesn't raise"""
        self.guc.group_gid_number = 5001
        del self.guc.members[0]['gidNumber']
        self.assertEqual(self.guc.primary_member_usernames, {'sdpoisson'})

    def test_add_new_projects(self):
        """unexpired pi group is added"""
        added_projects, _ = add_new_projects([self.guc], { 'no_pi': [], 'not_found': [] })
        self.assertEqual(len(added_projects), 1)

    def test_add_new_projects_pi_disabled(self):
        """group with disabled pi is not added"""
        self.disable_pi()
        added_projects, errortracker = add_new_projects([self.guc], { 'no_pi': [], 'not_found': [] })
        self.assertEqual(len(added_projects), 0)
        self.assertEqual(errortracker['no_pi'], ['bortkiewicz_lab'])

    def test_add_new_projects_pi_not_ifxuser(self):
        """project with a non-ifxuser pi is not added, and pi is added to the missing_users list"""
        get_user_model().objects.get(username='ljbortkiewicz').delete()
        new_projs, errortracker = add_new_projects([self.guc], { 'no_pi': [], 'not_found': [] })
        # no project added
        self.assertEqual(errortracker['no_pi'], ['bortkiewicz_lab'])
        self.assertEqual(len(new_projs), 0)
        # missing pi recorded
        missing_users_csv = './local_data/missing/missing_users.csv'
        missing_df = pd.read_csv(missing_users_csv, parse_dates=['date'])
        test_users = missing_df.loc[missing_df.username == 'ljbortkiewicz']
        self.assertEqual(len(test_users), 1)
        # remove test user from csv
        missing_df = missing_df.loc[~(missing_df.group == 'bortkiewicz_lab')]
        missing_df.to_csv(missing_users_csv, index=False)


def ad_user(username, enabled=True, gid_number=None):
    user = {'sAMAccountName': [username], 'userAccountControl': [512] if enabled else [514]}
    if gid_number is not None:
        user['gidNumber'] = [gid_number]
    return user


class CollectUpdateProjectStatusMembershipTests(TestCase):
    """Tests for collect_update_project_status_membership, the LDAP sync entry
    point responsible for keeping ProjectUser.status accurate against AD group
    membership (MemberOf) and account-disabled (userAccountControl) state."""

    def setUp(self):
        role_pi = ProjectUserRoleChoiceFactory(name='PI')
        self.role_user = ProjectUserRoleChoiceFactory(name='User')
        self.status_active = ProjectUserStatusChoiceFactory(name='Active')
        self.status_deactivated = ProjectUserStatusChoiceFactory(name='Deactivated')
        ProjectUserStatusChoiceFactory(name='Removed')
        AllocationUserStatusChoiceFactory(name='Active')
        AllocationUserStatusChoiceFactory(name='Removed')

        ProjectStatusChoiceFactory(name='Archived')

        self.pi_user = UserFactory(username='pi_user')
        self.project = ProjectFactory(
            title='test_lab', pi=self.pi_user, status=ProjectStatusChoiceFactory(name='Active')
        )
        ProjectUserFactory(
            project=self.project, user=self.pi_user, role=role_pi, status=self.status_active
        )

        self.user_becomes_disabled = UserFactory(username='user_becomes_disabled')
        self.pu_becomes_disabled = ProjectUserFactory(
            project=self.project, user=self.user_becomes_disabled,
            role=self.role_user, status=self.status_active,
        )

        self.user_becomes_enabled = UserFactory(username='user_becomes_enabled')
        self.pu_becomes_enabled = ProjectUserFactory(
            project=self.project, user=self.user_becomes_enabled,
            role=self.role_user, status=self.status_deactivated,
        )

        self.user_left_group = UserFactory(username='user_left_group')
        self.pu_left_group = ProjectUserFactory(
            project=self.project, user=self.user_left_group,
            role=self.role_user, status=self.status_active,
        )

        # not yet a ProjectUser at all - a disabled account newly seen in the group
        self.user_new_disabled = UserFactory(username='user_new_disabled')

        # the project's AD group's own gidNumber, used to determine primary-group membership
        self.group_gid_number = 5001

        self.user_primary_member = UserFactory(username='user_primary_member')
        self.pu_primary_member = ProjectUserFactory(
            project=self.project, user=self.user_primary_member,
            role=self.role_user, status=self.status_active, primary_group=False,
        )

        self.user_secondary_member = UserFactory(username='user_secondary_member')
        self.pu_secondary_member = ProjectUserFactory(
            project=self.project, user=self.user_secondary_member,
            role=self.role_user, status=self.status_active, primary_group=True,
        )

        self.ad_members = [
            ad_user(self.pi_user.username, enabled=True),
            ad_user(self.user_becomes_disabled.username, enabled=False),
            ad_user(self.user_becomes_enabled.username, enabled=True),
            ad_user(self.user_new_disabled.username, enabled=False),
            ad_user(
                self.user_primary_member.username, enabled=True,
                gid_number=self.group_gid_number,
            ),
            # secondary member's own primary AD group is a different one (9999)
            ad_user(self.user_secondary_member.username, enabled=True, gid_number=9999),
            # user_left_group is intentionally absent - no longer an AD member
        ]
        self.ad_manager = ad_user(self.pi_user.username, enabled=True)
        self.ad_group_entry = {
            'sAMAccountName': [self.project.title], 'gidNumber': [self.group_gid_number],
        }

    def run_sync(self):
        with patch('coldfront.plugins.ldap.utils.Server'), patch(
            'coldfront.plugins.ldap.utils.Connection'
        ), patch(
            'coldfront.plugins.ldap.utils.LDAPConn.return_group_members_manager',
            return_value=(self.ad_members, self.ad_manager),
        ), patch(
            'coldfront.plugins.ldap.utils.LDAPConn.return_group_by_name',
            return_value=self.ad_group_entry,
        ):
            collect_update_project_status_membership()

    def test_active_member_disabled_in_ad_becomes_deactivated(self):
        """Active ProjectUser whose AD account is disabled, but who remains a
        group member, should become Deactivated - not stay Active or become Removed."""
        self.run_sync()
        self.pu_becomes_disabled.refresh_from_db()
        self.assertEqual(self.pu_becomes_disabled.status.name, 'Deactivated')

    def test_deactivated_member_reenabled_in_ad_becomes_active(self):
        """Deactivated ProjectUser whose AD account is re-enabled, while still a
        group member, should become Active again."""
        self.run_sync()
        self.pu_becomes_enabled.refresh_from_db()
        self.assertEqual(self.pu_becomes_enabled.status.name, 'Active')

    def test_disabled_new_member_created_as_deactivated_not_active(self):
        """A disabled AD account newly seen as a group member should be created
        as Deactivated, not Active."""
        self.run_sync()
        new_pu = ProjectUser.objects.get(project=self.project, user=self.user_new_disabled)
        self.assertEqual(new_pu.status.name, 'Deactivated')

    def test_member_no_longer_in_ad_group_becomes_removed(self):
        """A ProjectUser with no corresponding AD group membership at all should
        become Removed, regardless of the new Deactivated handling."""
        self.run_sync()
        self.pu_left_group.refresh_from_db()
        self.assertEqual(self.pu_left_group.status.name, 'Removed')

    def test_member_with_matching_gid_becomes_primary_group(self):
        """A member whose AD gidNumber matches the project's AD group's own
        gidNumber should end up primary_group=True."""
        self.run_sync()
        self.pu_primary_member.refresh_from_db()
        self.assertTrue(self.pu_primary_member.primary_group)

    def test_member_with_different_gid_is_not_primary_group(self):
        """A member whose primary AD group is not this project's AD group
        should be (re)set to primary_group=False, even if it was True before."""
        self.run_sync()
        self.pu_secondary_member.refresh_from_db()
        self.assertFalse(self.pu_secondary_member.primary_group)

    def test_pi_unaffected_when_active_and_enabled(self):
        self.run_sync()
        pi_projectuser = self.project.projectuser_set.get(user=self.pi_user)
        self.assertEqual(pi_projectuser.status.name, 'Active')


@override_settings(
    LDAP_PROJECTUSER_AD_SYNC=True,
    EMAIL_ADMIN_LIST=['admin@example.org'],
    EMAIL_SENDER='coldfront@example.org',
)
class ProjectUserADSyncTests(TestCase):
    """Tests for writing ProjectUser status changes to AD from pre_save, and the retry task"""

    def setUp(self):
        self.user = UserFactory(username='sdpoisson')
        self.project = ProjectFactory(title='poisson_lab')
        self.statuses = {
            name: ProjectUserStatusChoiceFactory(name=name)
            for name in ['Active', 'Removed', 'Deactivated', 'Pending - Add', 'Pending - Remove']
        }
        apply_patcher = patch(
            'coldfront.plugins.ldap.projectuser_sync.apply_ad_intent',
            side_effect=lambda username, group_name, intent, *args: intent,
        )
        self.mock_apply = apply_patcher.start()
        self.addCleanup(apply_patcher.stop)
        task_patcher = patch('coldfront.plugins.ldap.projectuser_sync.async_task')
        self.mock_async_task = task_patcher.start()
        self.addCleanup(task_patcher.stop)

    def make_projectuser(self, status, project=None):
        projectuser = ProjectUserFactory(
            project=project or self.project, user=self.user, status=self.statuses[status]
        )
        self.mock_apply.reset_mock()
        return projectuser

    def set_status(self, projectuser, status, **attrs):
        projectuser.status = self.statuses[status]
        for name, value in attrs.items():
            setattr(projectuser, name, value)
        with self.captureOnCommitCallbacks(execute=True):
            projectuser.save()
        return projectuser

    def assert_applied(self, intent):
        self.mock_apply.assert_called_once()
        self.assertEqual(self.mock_apply.call_args.args[:3], ('sdpoisson', 'poisson_lab', intent))

    def test_new_removed_projectuser_makes_no_ad_change(self):
        ProjectUserFactory(project=self.project, user=self.user, status=self.statuses['Removed'])
        self.mock_apply.assert_not_called()

    def test_new_active_projectuser_added_to_group(self):
        ProjectUserFactory(project=self.project, user=self.user, status=self.statuses['Active'])
        self.assert_applied('add')

    def test_removed_to_active_adds_to_group(self):
        projectuser = self.make_projectuser('Removed')
        self.set_status(projectuser, 'Active')
        self.assert_applied('add')

    def test_deactivated_to_active_reactivates_account(self):
        projectuser = self.make_projectuser('Deactivated')
        with patch('coldfront.plugins.ldap.projectuser_sync.reactivate_user_groups') as mock_groups:
            self.set_status(projectuser, 'Active')
        self.assert_applied('reactivate')
        mock_groups.assert_called_once_with(self.user)

    def test_active_to_removed_removes_from_group(self):
        projectuser = self.make_projectuser('Active')
        self.set_status(projectuser, 'Removed', _ad_actor=('admin', '(Admin)'))
        self.assert_applied('remove')
        self.assertEqual(self.mock_apply.call_args.args[3:], ('admin', '(Admin)'))

    def test_active_to_deactivated_makes_no_ad_change(self):
        projectuser = self.make_projectuser('Active')
        self.set_status(projectuser, 'Deactivated')
        self.mock_apply.assert_not_called()

    def test_explicit_intent_overrides_mapping(self):
        projectuser = self.make_projectuser('Active')
        self.set_status(projectuser, 'Deactivated', _ad_intent='deactivate')
        self.assert_applied('deactivate')

    def test_unchanged_status_makes_no_ad_change(self):
        projectuser = self.make_projectuser('Active')
        projectuser.enable_notifications = False
        projectuser.save()
        self.mock_apply.assert_not_called()

    def test_skip_flag_makes_no_ad_change(self):
        projectuser = self.make_projectuser('Active')
        self.set_status(projectuser, 'Removed', _skip_ad_sync=True)
        self.mock_apply.assert_not_called()
        projectuser.refresh_from_db()
        self.assertEqual(projectuser.status.name, 'Removed')

    @override_settings(LDAP_PROJECTUSER_AD_SYNC=False)
    def test_disabled_setting_makes_no_ad_change(self):
        projectuser = self.make_projectuser('Active')
        self.set_status(projectuser, 'Removed')
        self.mock_apply.assert_not_called()

    def test_rejection_blocks_save(self):
        projectuser = self.make_projectuser('Active')
        self.mock_apply.side_effect = LDAPUserRemovalError('Member not successfully removed from group.')
        with self.assertRaises(ProjectUserStatusChangeError):
            self.set_status(projectuser, 'Removed')
        projectuser.refresh_from_db()
        self.assertEqual(projectuser.status.name, 'Active')
        self.mock_async_task.assert_not_called()

    def test_deactivated_account_rejection_keeps_its_type(self):
        projectuser = self.make_projectuser('Removed')
        self.mock_apply.side_effect = LDAPUserDeactivatedError('user is deactivated')
        with self.assertRaises(ProjectUserDeactivatedError):
            self.set_status(projectuser, 'Active')

    def test_unreachable_saves_pending_and_queues_task(self):
        projectuser = self.make_projectuser('Active')
        self.mock_apply.side_effect = LDAPSocketOpenError('unreachable')
        self.set_status(projectuser, 'Removed', _ad_actor=('admin', '(Admin)'))
        projectuser.refresh_from_db()
        self.assertEqual(projectuser.status.name, 'Pending - Remove')
        self.mock_async_task.assert_called_once_with(
            'coldfront.plugins.ldap.tasks.apply_projectuser_ad_change', projectuser.pk,
            intent='remove', previous_status='Active', target_status='Removed',
            actor_username='admin', actor_role='(Admin)', complete_removal=False,
        )

    def test_removal_status_follows_what_ad_applied(self):
        """The caller expected a primary-group deactivation, but AD only removed the membership"""
        projectuser = self.make_projectuser('Active')
        self.mock_apply.side_effect = lambda *args: 'remove'
        self.set_status(projectuser, 'Deactivated', _ad_intent='deactivate', _ad_complete_removal=True)
        projectuser.refresh_from_db()
        self.assertEqual(projectuser.status.name, 'Removed')

    def test_admin_removal_of_primary_group_deactivates_and_cascades(self):
        """An Active -> Removed edit where AD finds the primary group (so deactivates the
        account) saves Deactivated and deactivates the user's other projects"""
        other = ProjectUserFactory(
            project=ProjectFactory(title='gordon_lab'), user=self.user, status=self.statuses['Active']
        )
        projectuser = self.make_projectuser('Active')
        self.mock_apply.side_effect = lambda *args: 'deactivate'
        self.set_status(projectuser, 'Removed')
        projectuser.refresh_from_db()
        self.assertEqual(projectuser.status.name, 'Deactivated')
        other.refresh_from_db()
        self.assertEqual(other.status.name, 'Deactivated')

    def test_apply_ad_intent_reports_primary_group_removal(self):
        with patch('coldfront.plugins.ldap.projectuser_sync.LDAPConn') as mock_ldap_conn:
            mock_ldap_conn.return_value.is_primary_group.return_value = True
            self.assertEqual(real_apply_ad_intent('sdpoisson', 'poisson_lab', 'remove'), 'deactivate')
            mock_ldap_conn.return_value.is_primary_group.return_value = False
            self.assertEqual(real_apply_ad_intent('sdpoisson', 'poisson_lab', 'deactivate'), 'remove')
        self.assertEqual(mock_ldap_conn.return_value.remove_member_from_group.call_count, 2)

    def test_unreachable_new_projectuser_saved_pending_add(self):
        self.mock_apply.side_effect = LDAPSocketOpenError('unreachable')
        with self.captureOnCommitCallbacks(execute=True):
            projectuser = ProjectUserFactory(project=self.project, user=self.user, status=self.statuses['Active'])
        projectuser.refresh_from_db()
        self.assertEqual(projectuser.status.name, 'Pending - Add')
        self.assertIsNone(self.mock_async_task.call_args.kwargs['previous_status'])

    def test_filter_users_to_remove_falls_back_to_stored_primary_group(self):
        from coldfront.plugins.ldap.signals import filter_project_users_to_remove

        projectuser = self.make_projectuser('Active')
        projectuser.primary_group = True
        projectuser.save()
        other = UserFactory(username='other_user')
        ProjectUserFactory(project=self.project, user=other, status=self.statuses['Active'])
        users = [{'username': 'other_user'}, {'username': 'sdpoisson'}]
        with patch('coldfront.plugins.ldap.signals.LDAPConn', side_effect=LDAPSocketOpenError('unreachable')):
            result = filter_project_users_to_remove(sender=None, users_to_remove=users, project=self.project)
        self.assertEqual(
            [(u['username'], u['primary_group']) for u in result],
            [('sdpoisson', True), ('other_user', False)],
        )


@override_settings(
    LDAP_PROJECTUSER_AD_SYNC=True,
    EMAIL_ADMIN_LIST=['admin@example.org'],
    EMAIL_SENDER='coldfront@example.org',
    LDAP_PROJECTUSER_MAX_ATTEMPTS=3,
    LDAP_PROJECTUSER_RETRY_MINUTES=10,
)
class ApplyProjectUserADChangeTaskTests(TestCase):
    """Tests for the task that retries a queued ProjectUser AD change"""

    def setUp(self):
        self.user = UserFactory(username='sdpoisson')
        self.project = ProjectFactory(title='poisson_lab')
        self.statuses = {
            name: ProjectUserStatusChoiceFactory(name=name)
            for name in ['Active', 'Removed', 'Deactivated', 'Pending - Add', 'Pending - Remove']
        }
        echo_intent = lambda username, group_name, intent, *args: intent  # noqa: E731
        patchers = {
            'apply': patch('coldfront.plugins.ldap.tasks.apply_ad_intent', side_effect=echo_intent),
            'schedule': patch('coldfront.plugins.ldap.tasks.schedule'),
            'sync_apply': patch('coldfront.plugins.ldap.projectuser_sync.apply_ad_intent', side_effect=echo_intent),
        }
        self.mocks = {}
        for name, patcher in patchers.items():
            self.mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)

    def pending_projectuser(self, status='Pending - Remove', project=None):
        projectuser = ProjectUserFactory(
            project=project or self.project, user=self.user, status=self.statuses[status]
        )
        self.mocks['sync_apply'].reset_mock()
        return projectuser

    def run_task(
        self, projectuser, intent='remove', previous_status='Active', target_status='Removed',
        attempt=1, complete_removal=False,
    ):
        with self.captureOnCommitCallbacks(execute=True):
            apply_projectuser_ad_change(
                projectuser.pk, intent, previous_status, target_status, 'admin', '(Admin)', attempt,
                complete_removal=complete_removal,
            )
        projectuser.refresh_from_db()
        return projectuser

    def test_success_sets_target_status_without_another_ad_call(self):
        projectuser = self.run_task(self.pending_projectuser())
        self.assertEqual(projectuser.status.name, 'Removed')
        self.mocks['apply'].assert_called_once_with('sdpoisson', 'poisson_lab', 'remove', 'admin', '(Admin)')
        self.mocks['sync_apply'].assert_not_called()

    def test_deactivate_success_cascades_to_other_projects(self):
        other = ProjectUserFactory(
            project=ProjectFactory(title='gordon_lab'), user=self.user, status=self.statuses['Active']
        )
        projectuser = self.run_task(
            self.pending_projectuser(), intent='deactivate', target_status='Deactivated'
        )
        self.assertEqual(projectuser.status.name, 'Deactivated')
        other.refresh_from_db()
        self.assertEqual(other.status.name, 'Deactivated')

    def test_reactivate_success_reactivates_groups_and_storage(self):
        with patch('coldfront.plugins.ldap.projectuser_sync.reactivate_user_groups') as mock_groups, \
                patch('coldfront.plugins.ldap.projectuser_sync.reactivate_storage_allocationusers') as mock_storage:
            projectuser = self.run_task(
                self.pending_projectuser('Pending - Add'),
                intent='reactivate', previous_status='Deactivated', target_status='Active',
            )
        self.assertEqual(projectuser.status.name, 'Active')
        mock_groups.assert_called_once_with(self.user)
        mock_storage.assert_called_once_with(self.user)

    def test_still_unreachable_reschedules(self):
        self.mocks['apply'].side_effect = LDAPSocketOpenError('unreachable')
        projectuser = self.run_task(self.pending_projectuser(), attempt=2)
        self.assertEqual(projectuser.status.name, 'Pending - Remove')
        self.mocks['schedule'].assert_called_once()
        args = self.mocks['schedule'].call_args
        self.assertEqual(
            args.args,
            ('coldfront.plugins.ldap.tasks.apply_projectuser_ad_change', projectuser.pk, 'remove',
             'Active', 'Removed', 'admin', '(Admin)', 3),
        )
        self.assertEqual(args.kwargs['schedule_type'], Schedule.ONCE)
        self.assertEqual(args.kwargs['complete_removal'], False)

    def test_queued_removal_runs_view_follow_ups_when_asked(self):
        with patch(
            'coldfront.core.project.views.ProjectRemoveUsersView.complete_removal', return_value=([], [])
        ) as mock_complete:
            projectuser = self.run_task(self.pending_projectuser(), complete_removal=True)
        self.assertEqual(projectuser.status.name, 'Removed')
        mock_complete.assert_called_once_with(self.project, self.user, deactivated=False)

    def test_queued_removal_without_flag_skips_view_follow_ups(self):
        with patch('coldfront.core.project.views.ProjectRemoveUsersView.complete_removal') as mock_complete:
            self.run_task(self.pending_projectuser())
        mock_complete.assert_not_called()

    def test_queued_deactivation_follows_what_ad_applied(self):
        """Queued as a primary-group deactivation, but AD found it isn't the primary group"""
        other = ProjectUserFactory(
            project=ProjectFactory(title='gordon_lab'), user=self.user, status=self.statuses['Active']
        )
        self.mocks['apply'].side_effect = lambda *args: 'remove'
        with patch(
            'coldfront.core.project.views.ProjectRemoveUsersView.complete_removal', return_value=([], [])
        ) as mock_complete:
            projectuser = self.run_task(
                self.pending_projectuser(), intent='deactivate', target_status='Deactivated',
                complete_removal=True,
            )
        self.assertEqual(projectuser.status.name, 'Removed')
        mock_complete.assert_called_once_with(self.project, self.user, deactivated=False)
        other.refresh_from_db()
        self.assertEqual(other.status.name, 'Active')

    @patch('coldfront.core.utils.mail.EMAIL_ENABLED', True)
    def test_attempts_exhausted_reverts_and_emails(self):
        self.mocks['apply'].side_effect = LDAPSocketOpenError('unreachable')
        projectuser = self.run_task(self.pending_projectuser(), attempt=3)
        self.assertEqual(projectuser.status.name, 'Active')
        self.mocks['schedule'].assert_not_called()
        self.mocks['sync_apply'].assert_not_called()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['admin@example.org'])
        self.assertIn('AD unreachable after 3 attempts', mail.outbox[0].body)

    @patch('coldfront.core.utils.mail.EMAIL_ENABLED', True)
    def test_rejection_reverts_and_emails(self):
        self.mocks['apply'].side_effect = LDAPUserRemovalError('Member not successfully removed from group.')
        projectuser = self.run_task(self.pending_projectuser())
        self.assertEqual(projectuser.status.name, 'Active')
        self.mocks['schedule'].assert_not_called()
        self.assertIn('AD rejected the change', mail.outbox[0].body)

    def test_revert_of_new_projectuser_sets_removed(self):
        self.mocks['apply'].side_effect = LDAPUserDeactivatedError('user is deactivated')
        projectuser = self.run_task(
            self.pending_projectuser('Pending - Add'), intent='add', previous_status=None, target_status='Active'
        )
        self.assertEqual(projectuser.status.name, 'Removed')

    def test_superseded_change_is_skipped(self):
        projectuser = self.pending_projectuser('Active')
        projectuser = self.run_task(projectuser)
        self.assertEqual(projectuser.status.name, 'Active')
        self.mocks['apply'].assert_not_called()
