from datetime import datetime
from unittest.mock import patch
import pandas as pd

from ldap3.core.timezone import OffsetTzInfo
from django.test import TestCase, tag
from django.contrib.auth import get_user_model

from coldfront.core.project.models import ProjectUser
from coldfront.plugins.ldap.utils import (
    LDAPConn,
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
        with patch('coldfront.plugins.ldap.utils.Connection'), patch(
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
