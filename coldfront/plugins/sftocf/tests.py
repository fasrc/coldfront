from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from coldfront.core.utils.fasrc import read_json
from coldfront.plugins.sftocf.utils import push_cf
from coldfront.core.allocation.models import Allocation

class ConnectionTest(TestCase):
    def test_update_usage_value(self):
        '''test update_usage_value
        '''
# test_integration.py

class UploadTests(TestCase):
    '''Catch issues that may cause database not to upload properly.'''
    fixtures = [
            'coldfront/core/test_helpers/test_data/test_fixtures/field_of_science.json',
            'coldfront/core/test_helpers/test_data/test_fixtures/all_res_choices.json',
            'coldfront/core/test_helpers/test_data/test_fixtures/poisson_fixtures.json',
            'coldfront/core/test_helpers/test_data/test_fixtures/project_choices.json',
            ]
    pref = './coldfront/plugins/sftocf/tests/testdata/'

    def test_push_cf(self):
        push_cf(self.testfiles, False)


    def test_update_usage(self):
        content = read_json(f'{self.pref}poisson_lab_holysfdb10.json')
        statdicts = content['contents']
        errors = False
        unames = [d['username'] for d in content['contents']]
        models = get_user_model().objects.only('id','username')\
                .filter(username__in=unames)
        allocation = Allocation.objects.get(project_id=1)
        for statdict in statdicts:
            try:
                server_tier = content['server'] + '/' + content['tier']
                self.update_usage(models, statdict, allocation)
            except Exception as e:
                print('ERROR:', e)
                errors = True
        assert not errors
