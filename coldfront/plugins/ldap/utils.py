'''
utility functions for LDAP interaction
'''
import logging
from datetime import datetime

import ldap.filter
from django.db.models import Q
from ldap3 import Connection, Server, ALL_ATTRIBUTES

from coldfront.core.utils.common import import_from_settings
from coldfront.core.project.models import ( Project,
                                            ProjectUserRoleChoice,
                                            ProjectUserStatusChoice,
                                            ProjectUser)

today = datetime.today().strftime('%Y%m%d')


logger = logging.getLogger(__name__)
logger.propagate = False
logger.setLevel(logging.DEBUG)
filehandler = logging.FileHandler(f'logs/{today}-ldap.log', 'w')
logger.addHandler(filehandler)

class LDAPConn:

    def __init__(self):
        self.LDAP_SERVER_URI = import_from_settings('AUTH_LDAP_SERVER_URI', None)
        self.LDAP_BIND_DN = import_from_settings('AUTH_LDAP_BIND_DN', None)
        self.LDAP_BIND_PASSWORD = import_from_settings('AUTH_LDAP_BIND_PASSWORD', None)
        self.LDAP_USER_SEARCH_BASE = import_from_settings('AUTH_LDAP_USER_SEARCH_BASE', None)
        self.LDAP_GROUP_SEARCH_BASE = import_from_settings('AUTH_LDAP_GROUP_SEARCH_BASE', None)
        self.LDAP_CONNECT_TIMEOUT = 20
        self.LDAP_USE_SSL = import_from_settings('AUTH_LDAP_USE_SSL', False)

        self.server = Server(self.LDAP_SERVER_URI, use_ssl=self.LDAP_USE_SSL, connect_timeout=self.LDAP_CONNECT_TIMEOUT)
        self.conn = Connection(self.server, self.LDAP_BIND_DN, self.LDAP_BIND_PASSWORD, auto_bind=True)

    # def parse_ldap_entry(self, entry):
    #     '''convert attributes of a given
    #     '''
    #     entry_dict = json.loads(self.entries[0].entry_to_json()).get('attributes')
    #     for k, v in entry_dict.items():
    #         if 0 < len(v) < 2:
    #             entry_dict[k] = v[0]
    #         elif not v:
    #             entry_dict[k] = None
    #     return entry_dict


    def search(self, attr_search_dict, search_base, search_type='exact'):
        '''Run a search using ldap.filter.
        Specify attr_search_string_list like so:
        {'cn': 'Bob Smith', 'company': 'FAS'}
        '''
        filter_params = format_template_assertions(attr_search_dict, search_type=search_type)
        search_filter = ldap.filter.filter_format(**filter_params)
        search_parameters = {
            'search_base': search_base,
            'search_filter': search_filter,
            'attributes': ALL_ATTRIBUTES,
        }
        self.conn.search(**search_parameters)
        return self.conn.entries


    def search_users(self, attr_search_dict, search_type='exact'):
        '''search for users.
        '''
        user_entries = self.search( attr_search_dict,
                                    self.LDAP_USER_SEARCH_BASE,
                                    search_type=search_type)
        return user_entries

    def search_groups(self, attr_search_dict, search_type='exact'):
        '''search for groups.
        '''
        group_entries = self.search(attr_search_dict,
                                    self.LDAP_GROUP_SEARCH_BASE,
                                    search_type=search_type)
        return group_entries


def format_template_assertions(attr_search_dict, search_type='exact'):
    '''Format attr_search_string_dict into correct filter_template
    Parameters
    ----------
    attr_search_string_dict : dict
        format should be {'cn': 'Bob Smith', 'company': 'FAS'}
    search_type : str
        options are 'exact' or 'partial'

    Returns
    -------
    output should be dict formatted like {'filter_template': '(|(cn=%s)(company=%s))', 'assertion_values': ['Bob Smith', 'FAS']})

    '''
    match_type = {'exact':'%s', 'partial': '*%s*'}
    filter_template_vars = [f'({k}={match_type[search_type]})' for k in attr_search_dict.keys()]
    filter_template = ''.join(filter_template_vars)
    if len(filter_template_vars) > 1:
        filter_template = '(|'+filter_template+')'
    assertion_values = list(attr_search_dict.values())
    return {
            'filter_template': filter_template,
            'assertion_values': assertion_values
            }
