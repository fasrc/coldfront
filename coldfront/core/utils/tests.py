from django.test import TestCase
from django.core.management import call_command


class CommandsTestCase(TestCase):
    '''tests for utility commands'''
    # def test_import_allocations(self):
    #     ''' Test import_add_allocations command.
    #     confirm that:
    #     - projects that haven't been added get properly logged
    #     - allocations require dirpath values to be added
    #     - allocation pi gets added
    #     - allocation usage, users, user usage get added
    #     '''
    #
    #     opts = {'file':'coldfront/core/test_helpers/test_data/test_add_allocations.csv'}
        # import_report = call_command('import_add_allocations', **opts)
        # self.assertEqual(len(import_report['missing_projects']), 3)
