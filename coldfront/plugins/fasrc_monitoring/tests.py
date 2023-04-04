
from django.db.models import Count
from django.test import TestCase, Client
from django.urls import reverse, reverse_lazy
from django.contrib.auth import get_user_model

from coldfront.core.test_helpers import utils
from coldfront.plugins.fasrc_monitoring.utils import UIChecker

FIXTURES = [
        "coldfront/core/test_helpers/test_data/test_fixtures/resources.json",
        "coldfront/core/test_helpers/test_data/test_fixtures/poisson_fixtures.json",
        "coldfront/core/test_helpers/test_data/test_fixtures/admin_fixtures.json",
        "coldfront/core/test_helpers/test_data/test_fixtures/all_res_choices.json",
        "coldfront/core/test_helpers/test_data/test_fixtures/field_of_science.json",
        "coldfront/core/test_helpers/test_data/test_fixtures/project_choices.json",
        ]


class MonitorViewTest(TestCase):

    fixtures = FIXTURES

    def setUp(self):
        self.admin_user = get_user_model().objects.get(username='gvanrossum')
        self.project_pi = get_user_model().objects.get(username='sdpoisson')
        self.client = Client()

    def test_allocation_detail_access(self):
        '''Confirm that only admins can access the page
        '''
        # check that login is required
        utils.test_logged_out_redirect_to_login(self, "/monitor")
        # check access for admin
        self.client.force_login(self.admin_user,
                backend="django.contrib.auth.backends.ModelBackend")
        response = self.client.get('/monitor')
        self.assertEqual(response.status_code, 200)
        # existing project pi
        self.client.force_login(self.project_pi,
                backend="django.contrib.auth.backends.ModelBackend")
        response = self.client.get('/monitor')
        self.assertEqual(response.status_code, 404)
