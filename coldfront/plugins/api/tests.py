from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase, APIRequestFactory

from coldfront.core.test_helpers.factories import (
    setup_models,
    AllocationAttributeFactory,
    AllocationAttributeTypeFactory,
    AllocationFactory,
    AllocationStatusChoiceFactory,
    ResourceFactory,
)
from coldfront.core.allocation.models import Allocation
from coldfront.core.project.models import Project
from coldfront.plugins.api.management_commands import ALLOWED_MANAGEMENT_COMMANDS


class ColdfrontAPI(APITestCase):
    """Tests for the Coldfront rest API"""

    fixtures = [
        "coldfront/core/test_helpers/test_data/test_fixtures/ifx.json",
    ]

    @classmethod
    def setUpTestData(cls):
        """Create some test data"""
        setup_models(cls)
        cls.additional_allocations = [
            AllocationFactory() for i in list(range(50))
        ]

    def test_requires_login(self):
        """Test that the API requires authentication"""
        response = self.client.get('/api/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_allocation_request_api_permissions(self):
        """Test that accessing the allocation-request API view as an admin returns all
        allocations, and that accessing it as a user is forbidden"""
        # login as admin
        self.client.force_login(self.admin_user)
        response = self.client.get('/api/allocation-requests/', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.force_login(self.pi_user)
        response = self.client.get('/api/allocation-requests/', format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_allocation_api_permissions(self):
        """Test that accessing the allocation API view as an admin returns all
        allocations, and that accessing it as a user returns only the allocations
        for that user"""
        # login as admin
        self.client.force_login(self.admin_user)
        response = self.client.get('/api/allocations/', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), Allocation.objects.all().count())

        self.client.force_login(self.pi_user)
        response = self.client.get('/api/allocations/', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_project_api_permissions(self):
        """Confirm permissions for project API:
        admin user should be able to access everything
        Projectusers should be able to access only their projects
        """
        # login as admin
        self.client.force_login(self.admin_user)
        response = self.client.get('/api/projects/', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), Project.objects.all().count())

        self.client.force_login(self.pi_user)
        response = self.client.get('/api/projects/', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_user_api_permissions(self):
        """Test that accessing the user API view as an admin returns all
        allocations, and that accessing it as a user is forbidden"""
        # login as admin
        self.client.force_login(self.admin_user)
        response = self.client.get('/api/users/', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.force_login(self.pi_user)
        response = self.client.get('/api/users/', format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AllocationSerializerOptimizationTests(APITestCase):
    """Regression tests for AllocationViewSet's prefetch-based 'resource'/'path' fields.

    These fields are computed in the serializer from prefetched data instead of via
    Allocation.get_resources_as_string / Allocation.path directly (see
    quality_reports/plans/lovely-prancing-toast.md), so this confirms the values still
    match what those model properties themselves return.
    """

    @classmethod
    def setUpTestData(cls):
        setup_models(cls)
        cls.resource_1 = ResourceFactory(name='Test Resource A')
        cls.resource_2 = ResourceFactory(name='Test Resource B')
        cls.allocation = AllocationFactory(project=cls.project)
        cls.allocation.resources.set([cls.resource_1, cls.resource_2])

        subdirectory_type = AllocationAttributeTypeFactory(name='Subdirectory')
        AllocationAttributeFactory(
            allocation=cls.allocation,
            allocation_attribute_type=subdirectory_type,
            value='/some/subdirectory',
        )

    def test_resource_field_matches_model_property(self):
        self.client.force_login(self.admin_user)
        response = self.client.get('/api/allocations/', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        result = next(row for row in response.data if row['id'] == self.allocation.id)
        self.assertEqual(result['resource'], self.allocation.get_resources_as_string)

    def test_path_field_matches_model_property(self):
        self.client.force_login(self.admin_user)
        response = self.client.get('/api/allocations/', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        result = next(row for row in response.data if row['id'] == self.allocation.id)
        self.assertEqual(result['path'], self.allocation.path)
        self.assertEqual(result['path'], '/some/subdirectory')


class AllocationDefaultStatusFilterTests(APITestCase):
    """AllocationViewSet defaults to 'Active' allocations unless status is specified."""

    @classmethod
    def setUpTestData(cls):
        setup_models(cls)
        cls.expired_allocation = AllocationFactory(
            project=cls.project, status=AllocationStatusChoiceFactory(name='Expired')
        )

    def test_default_excludes_non_active(self):
        self.client.force_login(self.admin_user)
        response = self.client.get('/api/allocations/', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = [row['id'] for row in response.data]
        self.assertNotIn(self.expired_allocation.id, returned_ids)
        self.assertTrue(all(row['status'] == 'Active' for row in response.data))

    def test_explicit_status_overrides_default(self):
        self.client.force_login(self.admin_user)
        response = self.client.get('/api/allocations/', {'status': 'Expired'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = [row['id'] for row in response.data]
        self.assertIn(self.expired_allocation.id, returned_ids)

    def test_empty_status_returns_all(self):
        self.client.force_login(self.admin_user)
        response = self.client.get('/api/allocations/', {'status': ''}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = [row['id'] for row in response.data]
        self.assertIn(self.expired_allocation.id, returned_ids)

    def test_retrieve_by_id_ignores_default_status_filter(self):
        """Fetching a non-Active allocation directly by id should not 404."""
        self.client.force_login(self.admin_user)
        response = self.client.get(f'/api/allocations/{self.expired_allocation.id}/', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.expired_allocation.id)


class ColdfrontAPIUnusedAllocations(APITestCase):
    """Tests for unused allocations report API view"""
    @classmethod
    def setUpTestData(cls):
        """Create some test data"""
        setup_models(cls)
        cls.allocation_1 = AllocationFactory(created=timezone.now() - timedelta(days=130))
        cls.additional_allocations = [
            AllocationFactory() for i in list(range(50))
        ]

    def test_unusedallocation_api_permissions(self):
        """Only admins can access unused allocations view"""
        self.client.force_login(self.admin_user)
        response = self.client.get('/api/unused-allocations/', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.force_login(self.pi_user)
        response = self.client.get('/api/unused-allocations/', format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unusedallocation_api_contents(self):
        """Unused allocations view displays only storage allocations over 4 months old with
        <= 1MB of usage or no change in storage usage for at least one month
        """
        response = self.client.get('/api/unused-allocations/', format='json')

    def test_unusedallocation_api_fields(self):
        """Unused allocations view displays allocation id, allocation path, resource name,
        project title, date of last change to Quota_In_Bytes usage, and current value of
        Quota_In_Bytes usage.
        """
        response = self.client.get('/api/unused-allocations/', format='json')

    def test_unusedallocation_api_filters(self):
        """Unused allocations view has working filters for project title, resource name,
        how long the Quota_In_Bytes usage value has gone unchanged, and
        greater than/less than/equal options for Quota_In_Bytes usage value
        """
        response = self.client.get('/api/unused-allocations/', format='json')


class ManagementCommandAPITests(APITestCase):
    """Tests for the management-commands API view"""

    fixtures = [
        "coldfront/core/test_helpers/test_data/test_fixtures/ifx.json",
    ]

    @classmethod
    def setUpTestData(cls):
        setup_models(cls)

    def test_requires_superuser(self):
        """Non-superusers are forbidden from listing or running commands"""
        self.client.force_login(self.pi_user)

        response = self.client.get('/api/management-commands/', format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.post(
            '/api/management-commands/', {'command': 'pruneOrganizations'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_returns_allowlist(self):
        """Superusers can list the allowlisted command names"""
        self.client.force_login(self.admin_user)
        response = self.client.get('/api/management-commands/', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data['commands']), set(ALLOWED_MANAGEMENT_COMMANDS))

    def test_run_allowed_command(self):
        """Superusers can run an allowlisted command and get its captured output back"""
        self.client.force_login(self.admin_user)
        response = self.client.post(
            '/api/management-commands/', {'command': 'pruneOrganizations'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIn('organizations removed', response.data['output'])

    def test_rejects_disallowed_command(self):
        """Commands not on the allowlist are rejected without being run"""
        self.client.force_login(self.admin_user)
        with patch('coldfront.plugins.api.views.call_command') as mock_call_command:
            response = self.client.post(
                '/api/management-commands/', {'command': 'migrate'}, format='json'
            )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_call_command.assert_not_called()

    def test_rejects_missing_command_field(self):
        """A request with no command name is rejected"""
        self.client.force_login(self.admin_user)
        response = self.client.post('/api/management-commands/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_run_command_with_allowed_args(self):
        """Superusers can pass declared args through to an allowlisted command"""
        self.client.force_login(self.admin_user)
        response = self.client.post(
            '/api/management-commands/',
            {'command': 'createProductUsages', 'year': 2024, 'month': 3, 'overwrite': True},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIn('records successfully created', response.data['output'])

    def test_rejects_undeclared_arg(self):
        """Args not declared for a command are rejected without running it"""
        self.client.force_login(self.admin_user)
        with patch('coldfront.plugins.api.views.call_command') as mock_call_command:
            response = self.client.post(
                '/api/management-commands/', {'command': 'pruneOrganizations', 'year': 2024}, format='json'
            )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_call_command.assert_not_called()

    def test_rejects_invalid_arg_type(self):
        """An arg value that can't be coerced to its declared type is rejected"""
        self.client.force_login(self.admin_user)
        with patch('coldfront.plugins.api.views.call_command') as mock_call_command:
            response = self.client.post(
                '/api/management-commands/',
                {'command': 'createProductUsages', 'year': 'not-a-year'},
                format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_call_command.assert_not_called()
