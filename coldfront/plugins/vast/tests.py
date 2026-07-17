'''tests for VAST plugin'''

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from vastpy import RESTFailure

from coldfront.core.allocation.models import Allocation
from coldfront.core.test_helpers.factories import (
    AAttributeTypeFactory,
    AllocationAttributeFactory,
    AllocationAttributeTypeFactory,
    AllocationFactory,
    AllocationStatusChoiceFactory,
    ProjectFactory,
    RAttributeTypeFactory,
    ResourceAttributeFactory,
    ResourceAttributeTypeFactory,
    ResourceFactory,
)
from coldfront.plugins.vast.utils import (
    VastDirectoryQuota,
    get_vast_directory_stat,
    get_vast_quota_group,
    is_vast_path_ignored,
    sync_vast_resource_allocations,
    update_allocation_quota_and_usage,
)


def make_mock_quota_dict(path, hard_bytes, usage_bytes, group_name='poisson_lab'):
    """Build a dict standing in for a raw VAST userquotas API response entry."""
    return {
        'path': path,
        'hard_limit': hard_bytes,
        'used_capacity': usage_bytes,
        'entity': {
            'is_group': True,
            'identifier_type': 'groupname',
            'identifier': group_name,
        },
    }


def directory_not_found_error():
    return RESTFailure(
        'POST', 'folders/stat_path', None, 503,
        b'{"detail":"Template directory path wasn\'t found","code":"service_unavailable"}',
    )


TIB = 1024**4


class VastDirectoryQuotaTests(TestCase):
    """Tests for the VastDirectoryQuota wrapper in vast/utils.py"""

    def test_has_hard_limit_and_byte_fields(self):
        quota_dict = make_mock_quota_dict('/holylabs', TIB, TIB // 2)
        directory_quota = VastDirectoryQuota(quota_dict)
        self.assertTrue(directory_quota.has_hard_limit)
        self.assertEqual(directory_quota.hard_limit_bytes, TIB)
        self.assertEqual(directory_quota.usage_bytes, TIB // 2)

    def test_no_hard_limit(self):
        quota_dict = make_mock_quota_dict('/holylabs', None, 0)
        directory_quota = VastDirectoryQuota(quota_dict)
        self.assertFalse(directory_quota.has_hard_limit)


class GetVastQuotaGroupTests(TestCase):
    """Tests for get_vast_quota_group's identifier-type dispatch in vast/utils.py"""

    def test_groupname_identifier_returns_identifier_directly(self):
        quota_dict = make_mock_quota_dict('/holylabs', TIB, 0, group_name='poisson_lab')
        self.assertEqual(get_vast_quota_group(quota_dict), 'poisson_lab')

    def test_gid_identifier_resolves_via_ldap(self):
        quota_dict = {
            'path': '/holylabs',
            'hard_limit': TIB,
            'used_capacity': 0,
            'entity': {'is_group': True, 'identifier_type': 'gid', 'identifier': 1234},
        }
        mock_ldap = MagicMock()
        mock_ldap.search_groups.return_value = [{'sAMAccountName': ['poisson_lab']}]
        self.assertEqual(get_vast_quota_group(quota_dict, ldap_conn=mock_ldap), 'poisson_lab')
        mock_ldap.search_groups.assert_called_once_with(
            {'gidNumber': 1234}, attributes=['sAMAccountName']
        )

    def test_gid_identifier_unresolved_in_ldap_returns_none(self):
        quota_dict = {
            'path': '/holylabs',
            'hard_limit': TIB,
            'used_capacity': 0,
            'entity': {'is_group': True, 'identifier_type': 'gid', 'identifier': 9999},
        }
        mock_ldap = MagicMock()
        mock_ldap.search_groups.return_value = []
        self.assertIsNone(get_vast_quota_group(quota_dict, ldap_conn=mock_ldap))

    def test_unhandled_identifier_type_returns_none(self):
        quota_dict = {
            'path': '/holylabs',
            'hard_limit': TIB,
            'used_capacity': 0,
            'entity': {'is_group': True, 'identifier_type': 'sid', 'identifier': 'S-1-5-21'},
        }
        self.assertIsNone(get_vast_quota_group(quota_dict))


class GetVastDirectoryStatTests(TestCase):
    """Tests for get_vast_directory_stat's stat_path handling in vast/utils.py"""

    def test_present_directory_returns_stat_dict(self):
        stat = {'is_directory': True, 'owning_group': 'poisson_lab'}
        mock_client = MagicMock()
        mock_client.folders.stat_path.post.return_value = stat
        with patch('coldfront.plugins.vast.utils.client', mock_client):
            self.assertEqual(get_vast_directory_stat('/holylabs/C/poisson_lab'), stat)

    def test_missing_directory_returns_none(self):
        mock_client = MagicMock()
        mock_client.folders.stat_path.post.side_effect = directory_not_found_error()
        with patch('coldfront.plugins.vast.utils.client', mock_client):
            self.assertIsNone(get_vast_directory_stat('/holylabs/C/ghost_lab'))

    def test_other_failure_is_reraised(self):
        mock_client = MagicMock()
        mock_client.folders.stat_path.post.side_effect = RESTFailure(
            'POST', 'folders/stat_path', None, 401, b'{"detail":"Unauthorized"}'
        )
        with patch('coldfront.plugins.vast.utils.client', mock_client):
            with self.assertRaises(RESTFailure):
                get_vast_directory_stat('/holylabs/C/poisson_lab')


class SyncVastAllocationsTests(TestCase):
    """Tests for sync_vast_allocations reconciliation logic in vast/utils.py

    VAST quotas identify entities by project/group, not by a distinct
    per-allocation path - every quota under a resource reports the same shared
    view path (e.g. '/holylabs') regardless of which group it's for. So unlike
    isilon, allocation identity here is (project, resource); a project's
    directory is expected at '/holylabs/C/{project.title}', and its presence
    there (checked via folders.stat_path) gates both allocation
    creation/activation and deactivation.
    """

    def setUp(self):
        for status in ('Active', 'Inactive', 'New', 'On Hold', 'In Progress', 'Pending Activation', 'Denied'):
            AllocationStatusChoiceFactory(name=status)

        self.subdir_type = AllocationAttributeTypeFactory(
            name='Subdirectory', attribute_type=AAttributeTypeFactory(name='Text'), has_usage=False,
        )
        self.quota_bytes_type = AllocationAttributeTypeFactory(
            name='Quota_In_Bytes', attribute_type=AAttributeTypeFactory(name='Int'), has_usage=True,
        )
        self.quota_tib_type = AllocationAttributeTypeFactory(
            name='Storage Quota (TiB)', attribute_type=AAttributeTypeFactory(name='Float'), has_usage=True,
        )
        self.requires_payment_type = AllocationAttributeTypeFactory(
            name='RequiresPayment', attribute_type=AAttributeTypeFactory(name='Yes/No'), has_usage=False,
        )

        self.project = ProjectFactory(title='poisson_lab')
        self.resource = ResourceFactory(name='vast-holylabs', resource_type__name='Storage')
        ResourceAttributeFactory(
            resource=self.resource,
            resource_attribute_type=ResourceAttributeTypeFactory(
                name='storage_protocol', attribute_type=RAttributeTypeFactory(name='Text'),
            ),
            value='vast',
        )
        ResourceAttributeFactory(
            resource=self.resource,
            resource_attribute_type=ResourceAttributeTypeFactory(
                name='url', attribute_type=RAttributeTypeFactory(name='Text'),
            ),
            value='holylabs',
        )

    def sync_with_quotas(self, quotas, present_paths=None):
        """present_paths: set of full VAST paths (e.g. '/holylabs/C/poisson_lab')
        to treat as existing directories. A path not in this set raises the
        "not found" RESTFailure, matching real VAST behavior. If None (the
        default), every path is treated as present - convenient for tests that
        aren't specifically exercising the stat_path presence gate.
        """
        mock_client = MagicMock()
        mock_client.userquotas.get.return_value = quotas

        def stat_path_side_effect(path):
            if present_paths is None or path in present_paths:
                return {'is_directory': True, 'owning_group': 'placeholder'}
            raise directory_not_found_error()

        mock_client.folders.stat_path.post.side_effect = stat_path_side_effect

        with patch('coldfront.plugins.vast.utils.client', mock_client), \
             patch('coldfront.plugins.vast.utils.LDAPConn') as mock_ldap_cls:
            mock_ldap_cls.return_value = MagicMock()
            return sync_vast_resource_allocations(self.resource)

    def test_no_hard_limit_warns_and_is_skipped(self):
        quota = make_mock_quota_dict('/holylabs', None, 0, group_name='poisson_lab')
        report = self.sync_with_quotas([quota])
        self.assertIn('/holylabs', report['no_limit'])
        self.assertEqual(Allocation.objects.count(), 0)

    def test_no_hard_limit_ignored_path_not_warned(self):
        quota = make_mock_quota_dict('/holylabs', None, 0, group_name='poisson_lab')
        with override_settings(VAST_PATH_IGNORE=['/holylabs']):
            report = self.sync_with_quotas([quota])
        self.assertEqual(report['no_limit'], [])

    def test_no_hard_limit_does_not_deactivate_existing_allocation(self):
        allocation = AllocationFactory(project=self.project, status__name='Active')
        allocation.resources.add(self.resource)

        quota = make_mock_quota_dict('/holylabs', None, 0, group_name='poisson_lab')
        report = self.sync_with_quotas([quota])  # directory present by default

        self.assertEqual(report['deactivated'], [])
        allocation.refresh_from_db()
        self.assertEqual(allocation.status.name, 'Active')

    def test_group_without_matching_project_is_reported(self):
        quota = make_mock_quota_dict('/holylabs', TIB, 0, group_name='ghost_lab')
        report = self.sync_with_quotas([quota])
        self.assertIn('ghost_lab', report['missing_projects'])
        self.assertEqual(Allocation.objects.count(), 0)

    def test_unresolved_group_name_is_reported_not_crashed(self):
        quota = {
            'path': '/holylabs',
            'hard_limit': TIB,
            'used_capacity': 0,
            'entity': {'is_group': True, 'identifier_type': 'sid', 'identifier': 'S-1-5-21'},
        }
        report = self.sync_with_quotas([quota])
        self.assertIn('/holylabs', report['unresolved_group'])
        self.assertEqual(report['missing_projects'], [])

    def test_new_allocation_created_when_directory_present(self):
        quota = make_mock_quota_dict('/holylabs', TIB, TIB // 2)
        report = self.sync_with_quotas([quota], present_paths={'/holylabs/C/poisson_lab'})

        self.assertIn('poisson_lab', report['created'])
        allocation = Allocation.objects.get(project=self.project)
        self.assertEqual(allocation.status.name, 'Active')
        self.assertEqual(allocation.path, 'C/poisson_lab')
        self.assertEqual(
            int(float(allocation.get_attribute('Quota_In_Bytes', typed=False))), TIB
        )
        self.assertEqual(
            allocation.get_attribute('RequiresPayment', typed=False), str(self.resource.requires_payment)
        )

    def test_allocation_not_created_when_directory_missing(self):
        quota = make_mock_quota_dict('/holylabs', TIB, TIB // 2)
        report = self.sync_with_quotas([quota], present_paths=set())

        self.assertIn('poisson_lab', report['directory_missing'])
        self.assertEqual(report['created'], [])
        self.assertEqual(Allocation.objects.count(), 0)

    def test_existing_allocation_is_updated_not_duplicated(self):
        allocation = AllocationFactory(project=self.project, status__name='Active')
        allocation.resources.add(self.resource)
        AllocationAttributeFactory(
            allocation=allocation, allocation_attribute_type=self.subdir_type, value='C/poisson_lab',
        )

        quota = make_mock_quota_dict('/holylabs', TIB, TIB // 2)
        report = self.sync_with_quotas([quota], present_paths={'/holylabs/C/poisson_lab'})

        self.assertIn('poisson_lab', report['updated'])
        self.assertEqual(Allocation.objects.filter(project=self.project).count(), 1)
        allocation.refresh_from_db()
        self.assertEqual(
            int(float(allocation.get_attribute('Quota_In_Bytes', typed=False))), TIB
        )
        self.assertEqual(allocation.status.name, 'Active')

    def test_pending_allocation_request_is_activated(self):
        pending = AllocationFactory(
            project=self.project, status__name='New', justification='requesting storage',
        )
        pending.resources.add(self.resource)
        AllocationAttributeFactory(
            allocation=pending, allocation_attribute_type=self.quota_tib_type, value=1.0,
        )

        quota = make_mock_quota_dict('/holylabs', TIB, TIB // 2)
        report = self.sync_with_quotas([quota], present_paths={'/holylabs/C/poisson_lab'})

        self.assertIn('poisson_lab', report['activated'])
        self.assertEqual(Allocation.objects.filter(project=self.project).count(), 1)
        pending.refresh_from_db()
        self.assertEqual(pending.status.name, 'Active')
        self.assertEqual(pending.path, 'C/poisson_lab')
        self.assertEqual(
            pending.get_attribute('RequiresPayment', typed=False), str(self.resource.requires_payment)
        )

    def test_pending_request_not_activated_when_directory_missing(self):
        pending = AllocationFactory(
            project=self.project, status__name='New', justification='requesting storage',
        )
        pending.resources.add(self.resource)
        AllocationAttributeFactory(
            allocation=pending, allocation_attribute_type=self.quota_tib_type, value=1.0,
        )

        quota = make_mock_quota_dict('/holylabs', TIB, TIB // 2)
        report = self.sync_with_quotas([quota], present_paths=set())

        self.assertIn('poisson_lab', report['directory_missing'])
        self.assertEqual(report['activated'], [])
        pending.refresh_from_db()
        self.assertEqual(pending.status.name, 'New')

    def test_pending_request_on_tier_resource_is_not_matched(self):
        tier_resource = ResourceFactory(name='Tier 0', resource_type__name='Storage Tier')
        self.resource.parent_resource = tier_resource
        self.resource.save()

        pending = AllocationFactory(
            project=self.project, status__name='New', justification='requesting tier 0 storage',
        )
        pending.resources.add(tier_resource)
        AllocationAttributeFactory(
            allocation=pending, allocation_attribute_type=self.quota_tib_type, value=1.0,
        )

        quota = make_mock_quota_dict('/holylabs', TIB, TIB // 2)
        report = self.sync_with_quotas([quota], present_paths={'/holylabs/C/poisson_lab'})

        # the tier-attached request must NOT be matched - a new allocation is created instead
        self.assertIn('poisson_lab', report['created'])
        pending.refresh_from_db()
        self.assertEqual(pending.status.name, 'New')
        self.assertEqual(Allocation.objects.filter(project=self.project).count(), 2)

    def test_update_allocation_quota_and_usage_skips_rewrite_when_unchanged(self):
        allocation = AllocationFactory(project=self.project, status__name='Active')
        allocation.resources.add(self.resource)

        changed = update_allocation_quota_and_usage(allocation, TIB, 100)
        self.assertTrue(changed)
        bytes_attr = allocation.allocationattribute_set.get(allocation_attribute_type=self.quota_bytes_type)
        history_count = bytes_attr.history.count()

        changed_again = update_allocation_quota_and_usage(allocation, TIB, 200)
        self.assertFalse(changed_again)
        bytes_attr.refresh_from_db()
        self.assertEqual(int(float(bytes_attr.value)), TIB)
        self.assertEqual(bytes_attr.allocationattributeusage.value, 200)
        self.assertEqual(bytes_attr.history.count(), history_count)

    def test_is_vast_path_ignored(self):
        self.assertFalse(is_vast_path_ignored('/holylabs'))
        with override_settings(VAST_PATH_IGNORE=['/holylabs']):
            self.assertTrue(is_vast_path_ignored('/holylabs'))

    def test_active_allocation_deactivated_when_directory_missing(self):
        ghost_project = ProjectFactory(title='ghost_lab')
        allocation = AllocationFactory(project=ghost_project, status__name='Active')
        allocation.resources.add(self.resource)

        # ghost_lab's directory doesn't exist, even though poisson_lab's does -
        # deactivation is driven by stat_path, not by userquotas list membership
        quota = make_mock_quota_dict('/holylabs', TIB, TIB // 2, group_name='poisson_lab')
        report = self.sync_with_quotas([quota], present_paths={'/holylabs/C/poisson_lab'})

        self.assertIn('ghost_lab', report['deactivated'])
        allocation.refresh_from_db()
        self.assertEqual(allocation.status.name, 'Inactive')

    def test_active_allocation_with_present_directory_is_not_deactivated(self):
        allocation = AllocationFactory(project=self.project, status__name='Active')
        allocation.resources.add(self.resource)

        quota = make_mock_quota_dict('/holylabs', TIB, TIB // 2, group_name='poisson_lab')
        report = self.sync_with_quotas([quota], present_paths={'/holylabs/C/poisson_lab'})

        self.assertEqual(report['deactivated'], [])
        allocation.refresh_from_db()
        self.assertEqual(allocation.status.name, 'Active')

    def test_active_allocation_deactivated_even_if_absent_from_quota_list(self):
        # ghost_lab never appears in userquotas at all this run (not just
        # unresolved/missing-project - it's simply not in the list), but its
        # directory is still checked and found missing
        ghost_project = ProjectFactory(title='ghost_lab')
        allocation = AllocationFactory(project=ghost_project, status__name='Active')
        allocation.resources.add(self.resource)

        report = self.sync_with_quotas([], present_paths=set())

        self.assertIn('ghost_lab', report['deactivated'])
        allocation.refresh_from_db()
        self.assertEqual(allocation.status.name, 'Inactive')

    def test_active_allocation_on_other_resource_is_not_deactivated(self):
        other_resource = ResourceFactory(name='vast-otherlabs', resource_type__name='Storage')
        allocation = AllocationFactory(project=self.project, status__name='Active')
        allocation.resources.add(other_resource)

        # empty quota list for self.resource shouldn't touch allocations on a different resource
        report = self.sync_with_quotas([], present_paths=set())

        self.assertEqual(report['deactivated'], [])
        allocation.refresh_from_db()
        self.assertEqual(allocation.status.name, 'Active')
