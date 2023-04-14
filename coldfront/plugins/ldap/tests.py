from datetime import datetime

from ldap3 import OffsetTzInfo
from django.test import TestCase
from django.contrib.auth import get_user_model

from coldfront.plugins.ldap.utils import (format_template_assertions,
                                        LDAPConn, GroupUserCollection)

class UtilFunctionTests(TestCase):

    def test_format_template_assertions_one_kv(self):
        '''Format attr_search_dict with one key-value pair into correct filter_template input
        '''
        test_data = {'company': 'FAS'}
        desired_output = '(company=FAS)'
        output = format_template_assertions(test_data)
        self.assertEqual(output, desired_output)

    def test_format_template_assertions_multi_kv(self):
        '''Format attr_search_dict with multiple key-value pairs into correct filter_template input
        '''
        test_data = {'cn': 'Bob Smith', 'company': 'FAS'}
        desired_output = '(&(cn=Bob Smith)(company=FAS))'
        output = format_template_assertions(test_data)
        self.assertEqual(output, desired_output)


class LDAPConnTest(TestCase):
    '''tests for LDAPConn class'''

    def setUp(self):
        self.ldap_conn = LDAPConn()

    def test_search_group_one_kv(self):
        '''Be able to return correct group with the variables given
        '''
        attr_search_dict = {'sAMAccountName': 'rc_test_lab'}
        results = self.ldap_conn.search_groups(attr_search_dict)
        self.assertEqual(len(results), 1)


    def test_search_user_one_kv(self):
        '''Be able to return correct user with the variables given
        '''
        attr_search_dict = {'sAMAccountName': 'atestaccount'}
        results = self.ldap_conn.search_users(attr_search_dict)
        self.assertEqual(len(results), 1)

    def test_search_user_membership(self):
        '''Be able to return correct user with the variables given
        '''
        attr_search_dict = {'memberOf': 'CN=rc_test_lab,OU=RC,OU=Domain Groups,DC=rc,DC=domain'}
        results = self.ldap_conn.search_users(attr_search_dict)
        self.assertEqual(len(results), 5)

    def test_return_group_members(self):
        samaccountname = 'rc_test_lab'
        members = self.ldap_conn.return_group_members(samaccountname)
        self.assertEqual(len(members), 5)

class GroupUserCollectionTests(TestCase):
    '''Tests for GroupUserCollection class'''

    def setUp(self):
        group_name = 'poisson_lab'
        currentuser_accountExpires = [datetime(9999, 12, 31, 23, 59, 59, 999999, tzinfo=OffsetTzInfo(offset=0, name='UTC'))]
        ad_users = [
            {
                'sAMAccountName': ['ljbortkiewicz'],
                'accountExpires': currentuser_accountExpires,
            },
            {
                'sAMAccountName': ['sdpoisson'],
                'accountExpires': currentuser_accountExpires,
            },
            {
                'sAMAccountName': ['snewcomb'],
                'accountExpires': currentuser_accountExpires,
            },
        ]
        pi = {
            'sAMAccountName': ['sdpoisson'],
            'accountExpires': currentuser_accountExpires,
        }
        self.guc = (GroupUserCollection(group_name, ad_users, pi))

    def test_pi_is_active(self):
        self.assertEqual(self.guc.pi_is_active, True)

    def test_current_ad_users(self):
        self.assertEqual(len(self.guc.current_ad_users), 3)
