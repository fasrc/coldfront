from django.test import TestCase
from django.contrib.auth import get_user_model

from coldfront.plugins.ldap.utils import format_template_assertions, LDAPConn

class UtilFunctionTests(TestCase):

    def test_format_template_assertions_one_kv(self):
        '''Format attr_search_dict with one key-value pair into correct filter_template input
        '''
        test_data = {'company': 'FAS'}
        desired_output = {'filter_template': '(company=%s)', 'assertion_values': ['FAS']}
        output = format_template_assertions(test_data)
        self.assertEqual(output, desired_output)

    def test_format_template_assertions_multi_kv(self):
        '''Format attr_search_dict with multiple key-value pairs into correct filter_template input
        '''
        test_data = {'cn': 'Bob Smith', 'company': 'FAS'}
        desired_output = {
                'filter_template': '(|(cn=%s)(company=%s))',
                'assertion_values': ['Bob Smith', 'FAS']
                }
        output = format_template_assertions(test_data)
        self.assertEqual(output, desired_output)



class LDAPConnTest(TestCase):
    '''tests for LDAPConn class'''

    def setUp(self):
        self.ldap_conn = LDAPConn()

    def test_search_function_user_one_kv(self):
        '''Be able to return correct user with the variables given
        '''
        attr_search_dict = {'sAMAccountName': 'atestaccount'}
        results = self.ldap_conn.search(attr_search_dict, self.ldap_conn.LDAP_USER_SEARCH_BASE)
        self.assertEqual(len(results), 1)
