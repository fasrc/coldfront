'''tests for VAST plugin'''

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

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


TIB = 1024**4


class VastDirectoryQuotaTests(TestCase):
    """Tests for the VastDirectoryQuota wrapper in vast/utils.py"""

    def test_has_hard_limit_and_byte_fields(self):
        quota_dict = make_mock_quota_dict('/holylabs/poisson_lab', TIB, TIB // 2)
        directory_quota = VastDirectoryQuota(quota_dict)
        self.assertTrue(directory_quota.has_hard_limit)
        self.assertEqual(directory_quota.hard_limit_bytes, TIB)
        self.assertEqual(directory_quota.usage_bytes, TIB // 2)

    def test_no_hard_limit(self):
        quota_dict = make_mock_quota_dict('/holylabs/scratch_tmp', None, 0)
        directory_quota = VastDirectoryQuota(quota_dict)
        self.assertFalse(directory_quota.has_hard_limit)

    def test_cf_path_strips_leading_slash(self):
        quota_dict = make_mock_quota_dict('/holylabs/poisson_lab', TIB, 0)
        self.assertEqual(VastDirectoryQuota(quota_dict).cf_path, 'holylabs/poisson_lab')


class GetVastQuotaGroupTests(TestCase):
    """Tests for get_vast_quota_group's identifier-type dispatch in vast/utils.py"""

    def test_groupname_identifier_returns_identifier_directly(self):
        quota_dict = make_mock_quota_dict('/holylabs/poisson_lab', TIB, 0, group_name='poisson_lab')
        self.assertEqual(get_vast_quota_group(quota_dict), 'poisson_lab')

    def test_gid_identifier_resolves_via_ldap(self):
        quota_dict = {
            'path': '/holylabs/poisson_lab',
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
            'path': '/holylabs/ghost_lab',
            'hard_limit': TIB,
            'used_capacity': 0,
            'entity': {'is_group': True, 'identifier_type': 'gid', 'identifier': 9999},
        }
        mock_ldap = MagicMock()
        mock_ldap.search_groups.return_value = []
        self.assertIsNone(get_vast_quota_group(quota_dict, ldap_conn=mock_ldap))

    def test_unhandled_identifier_type_returns_none(self):
        quota_dict = {
            'path': '/holylabs/poisson_lab',
            'hard_limit': TIB,
            'used_capacity': 0,
            'entity': {'is_group': True, 'identifier_type': 'sid', 'identifier': 'S-1-5-21'},
        }
        self.assertIsNone(get_vast_quota_group(quota_dict))


class SyncVastAllocationsTests(TestCase):
    """Tests for sync_vast_allocations reconciliation logic in vast/utils.py"""

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

    def sync_with_quotas(self, quotas):
        mock_client = MagicMock()
        mock_client.userquotas.get.return_value = quotas
        with patch('coldfront.plugins.vast.utils.client', mock_client), \
             patch('coldfront.plugins.vast.utils.LDAPConn') as mock_ldap_cls:
            mock_ldap_cls.return_value = MagicMock()
            return sync_vast_resource_allocations(self.resource)

    def test_no_hard_limit_warns_and_is_skipped(self):
        quota = make_mock_quota_dict('/holylabs/scratch_tmp', None, 0)
        report = self.sync_with_quotas([quota])
        self.assertIn('/holylabs/scratch_tmp', report['no_limit'])
        self.assertEqual(Allocation.objects.count(), 0)

    def test_no_hard_limit_ignored_path_not_warned(self):
        quota = make_mock_quota_dict('/holylabs/scratch_tmp', None, 0)
        with override_settings(VAST_PATH_IGNORE=['/holylabs/scratch_tmp']):
            report = self.sync_with_quotas([quota])
        self.assertEqual(report['no_limit'], [])

    def test_group_without_matching_project_is_reported(self):
        quota = make_mock_quota_dict('/holylabs/ghost_lab', TIB, 0, group_name='ghost_lab')
        report = self.sync_with_quotas([quota])
        self.assertIn('ghost_lab', report['missing_projects'])
        self.assertEqual(Allocation.objects.count(), 0)

    def test_unresolved_group_name_is_reported_not_crashed(self):
        quota = {
            'path': '/holylabs/orphaned_dir',
            'hard_limit': TIB,
            'used_capacity': 0,
            'entity': {'is_group': True, 'identifier_type': 'sid', 'identifier': 'S-1-5-21'},
        }
        report = self.sync_with_quotas([quota])
        self.assertIn('/holylabs/orphaned_dir', report['unresolved_group'])
        self.assertEqual(report['missing_projects'], [])

    def test_new_allocation_created_when_none_exists(self):
        quota = make_mock_quota_dict('/holylabs/poisson_lab', TIB, TIB // 2)
        report = self.sync_with_quotas([quota])

        self.assertIn('holylabs/poisson_lab', report['created'])
        allocation = Allocation.objects.get(project=self.project)
        self.assertEqual(allocation.status.name, 'Active')
        self.assertEqual(allocation.path, 'holylabs/poisson_lab')
        self.assertEqual(
            int(float(allocation.get_attribute('Quota_In_Bytes', typed=False))), TIB
        )
        self.assertEqual(
            allocation.get_attribute('RequiresPayment', typed=False), str(self.resource.requires_payment)
        )

    def test_existing_allocation_is_updated_not_duplicated(self):
        allocation = AllocationFactory(project=self.project, status__name='Active')
        allocation.resources.add(self.resource)
        AllocationAttributeFactory(
            allocation=allocation, allocation_attribute_type=self.subdir_type, value='holylabs/poisson_lab',
        )

        quota = make_mock_quota_dict('/holylabs/poisson_lab', TIB, TIB // 2)
        report = self.sync_with_quotas([quota])

        self.assertIn('holylabs/poisson_lab', report['updated'])
        self.assertEqual(Allocation.objects.filter(project=self.project).count(), 1)
        allocation.refresh_from_db()
        self.assertEqual(
            int(float(allocation.get_attribute('Quota_In_Bytes', typed=False))), TIB
        )

    def test_pending_allocation_request_is_activated(self):
        pending = AllocationFactory(
            project=self.project, status__name='New', justification='requesting storage',
        )
        pending.resources.add(self.resource)
        AllocationAttributeFactory(
            allocation=pending, allocation_attribute_type=self.quota_tib_type, value=1.0,
        )

        quota = make_mock_quota_dict('/holylabs/poisson_lab', TIB, TIB // 2)
        report = self.sync_with_quotas([quota])

        self.assertIn('holylabs/poisson_lab', report['activated'])
        self.assertEqual(Allocation.objects.filter(project=self.project).count(), 1)
        pending.refresh_from_db()
        self.assertEqual(pending.status.name, 'Active')
        self.assertEqual(pending.path, 'holylabs/poisson_lab')
        self.assertEqual(
            pending.get_attribute('RequiresPayment', typed=False), str(self.resource.requires_payment)
        )

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

        quota = make_mock_quota_dict('/holylabs/poisson_lab', TIB, TIB // 2)
        report = self.sync_with_quotas([quota])

        # the tier-attached request must NOT be matched - a new allocation is created instead
        self.assertIn('holylabs/poisson_lab', report['created'])
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
        self.assertFalse(is_vast_path_ignored('/holylabs/poisson_lab'))
        with override_settings(VAST_PATH_IGNORE=['/holylabs/poisson_lab']):
            self.assertTrue(is_vast_path_ignored('/holylabs/poisson_lab'))

    def test_active_allocation_missing_from_volume_is_deactivated(self):
        allocation = AllocationFactory(project=self.project, status__name='Active')
        allocation.resources.add(self.resource)
        AllocationAttributeFactory(
            allocation=allocation, allocation_attribute_type=self.subdir_type, value='holylabs/ghost_lab',
        )

        quota = make_mock_quota_dict('/holylabs/poisson_lab', TIB, TIB // 2)
        report = self.sync_with_quotas([quota])

        self.assertIn('holylabs/ghost_lab', report['deactivated'])
        allocation.refresh_from_db()
        self.assertEqual(allocation.status.name, 'Inactive')

    def test_active_allocation_still_on_volume_is_not_deactivated(self):
        allocation = AllocationFactory(project=self.project, status__name='Active')
        allocation.resources.add(self.resource)
        AllocationAttributeFactory(
            allocation=allocation, allocation_attribute_type=self.subdir_type, value='holylabs/poisson_lab',
        )

        # quota still exists on the volume, just with no hard limit set
        quota = make_mock_quota_dict('/holylabs/poisson_lab', None, 0)
        report = self.sync_with_quotas([quota])

        self.assertEqual(report['deactivated'], [])
        allocation.refresh_from_db()
        self.assertEqual(allocation.status.name, 'Active')

    def test_active_allocation_with_no_path_is_not_deactivated(self):
        allocation = AllocationFactory(project=self.project, status__name='Active')
        allocation.resources.add(self.resource)

        report = self.sync_with_quotas([])

        self.assertEqual(report['deactivated'], [])
        allocation.refresh_from_db()
        self.assertEqual(allocation.status.name, 'Active')
