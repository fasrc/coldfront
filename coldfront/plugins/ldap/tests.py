from django.test import TestCase
from django.contrib.auth import get_user_model

from coldfront.plugins.ldap.utils import format_template_assertions, LDAPConn

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
