'''tests for Isilon plugin'''

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from coldfront.core.allocation.models import Allocation, AllocationStatusChoice
from coldfront.core.project.models import Project
from coldfront.core.resource.models import Resource
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
from coldfront.plugins.isilon.utils import (
    IsilonConnection,
    IsilonDirectoryQuota,
    create_isilon_allocation_quota,
    get_isilon_url,
    is_isilon_path_ignored,
    sync_isilon_resource_allocations,
    update_allocation_quota_and_usage,
)


def test_create_isilon_allocation_quota():
    """test create_isilon_connection
    uses cftest_lab to test
    """
    # create dummy allocation for cftest_lab
    allocation = Allocation(
        project=Project.objects.get(title='cftest_lab'),
        status=AllocationStatusChoice.objects.get(name='New'),
    )

    path = f'ifs/rc_labs/{allocation.project.title}'
    # for each isilon cluster:
    for resource in Resource.objects.filter(resourceattribute__value__in=('isilon', 'powerscale')):
        # create isilon IsilonConnection
        isilon_connection = IsilonConnection(get_isilon_url(resource))
        # run create_isilon_allocation_quota on the allocation with the isilon cluster
        create_isilon_allocation_quota(allocation, resource)

        # check that the directory acl is properly created
        acl = isilon_connection.namespace_client.get_acl(
            namespace_path=path,
            acl=True,
        )
        # confirm that acl mode is 2770
        assert acl.mode == '2770'
        # check that the directory quota is properly created
        quota_list = isilon_connection.quota_client.list_quota_quotas()
        quota = next(q for q in quota_list.quotas if q.path == f'/{path}')
        assert quota.thresholds.hard == 1099511627776
        print(quota)

        # check that the snapshot schedule is properly created
        schedules = isilon_connection.snapshot_client.list_snapshot_schedules()
        snapshot_schedule = next(
            s for s in schedules.schedules if s.path == f'/{path}')
        print(snapshot_schedule)

        # check that the nfs export is properly created
        exports = isilon_connection.nfs_client.list_nfs_exports()
        export = next(e for e in exports.exports if e.path == f'/{path}')
        print(export)
        # check that the smb share is properly created
        shares = isilon_connection.smb_client.list_smb_shares()
        share = next(s for s in shares.shares if s.path == f'/{path}')
        print(share)
        
        # delete the quota
        isilon_connection.quota_client.delete_quota_quota(
            path=f'/{path}',
        )


        # delete the directory
        isilon_connection.namespace_client.delete_directory(path)


def make_mock_quota(path, hard_bytes, usage_bytes):
    """Build a MagicMock standing in for an isilon_sdk SmartQuota object."""
    quota = MagicMock()
    quota.path = path
    quota.thresholds.hard = hard_bytes
    quota.usage.fslogical = usage_bytes
    return quota


TIB = 1024**4


class IsilonDirectoryQuotaTests(TestCase):
    """Tests for the IsilonDirectoryQuota wrapper in isilon/utils.py"""

    def test_has_hard_limit_and_byte_fields(self):
        quota = make_mock_quota('/ifs/rc_labs/poisson_lab', TIB, TIB // 2)
        directory_quota = IsilonDirectoryQuota(quota)
        self.assertTrue(directory_quota.has_hard_limit)
        self.assertEqual(directory_quota.hard_limit_bytes, TIB)
        self.assertEqual(directory_quota.usage_bytes, TIB // 2)

    def test_no_hard_limit(self):
        quota = make_mock_quota('/ifs/rc_labs/scratch_tmp', None, 0)
        directory_quota = IsilonDirectoryQuota(quota)
        self.assertFalse(directory_quota.has_hard_limit)

    def test_cf_path_strips_leading_ifs(self):
        quota = make_mock_quota('/ifs/rc_labs/poisson_lab', TIB, 0)
        self.assertEqual(IsilonDirectoryQuota(quota).cf_path, 'rc_labs/poisson_lab')

    def test_cf_path_without_leading_ifs(self):
        quota = make_mock_quota('rc_fasse_labs/poisson_lab', TIB, 0)
        self.assertEqual(IsilonDirectoryQuota(quota).cf_path, 'rc_fasse_labs/poisson_lab')


class SyncIsilonAllocationsTests(TestCase):
    """Tests for sync_isilon_allocations reconciliation logic in isilon/utils.py"""

    def setUp(self):
        for status in ('Active', 'New', 'On Hold', 'In Progress', 'Pending Activation', 'Denied'):
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

        self.project = ProjectFactory(title='poisson_lab')
        self.resource = ResourceFactory(name='isilon01', resource_type__name='Storage')
        ResourceAttributeFactory(
            resource=self.resource,
            resource_attribute_type=ResourceAttributeTypeFactory(
                name='storage_protocol', attribute_type=RAttributeTypeFactory(name='Text'),
            ),
            value='isilon',
        )
        ResourceAttributeFactory(
            resource=self.resource,
            resource_attribute_type=ResourceAttributeTypeFactory(
                name='url', attribute_type=RAttributeTypeFactory(name='Text'),
            ),
            value='https://isilon01.example.edu:8080',
        )

    def sync_with_quotas(self, quotas, group_name='poisson_lab'):
        mock_conn = MagicMock()
        mock_conn.quota_client.list_quota_quotas.return_value.quotas = quotas
        mock_conn.namespace_client.get_acl.return_value.group.name = group_name
        with patch('coldfront.plugins.isilon.utils.IsilonConnection', return_value=mock_conn):
            return sync_isilon_resource_allocations(self.resource)

    def test_no_hard_limit_warns_and_is_skipped(self):
        quota = make_mock_quota('/ifs/rc_labs/scratch_tmp', None, 0)
        report = self.sync_with_quotas([quota])
        self.assertIn('/ifs/rc_labs/scratch_tmp', report['no_limit'])
        self.assertEqual(Allocation.objects.count(), 0)

    @override_settings(ISILON_PATH_IGNORE=['/ifs/rc_labs/scratch_tmp'])
    def test_no_hard_limit_ignored_path_not_warned(self):
        quota = make_mock_quota('/ifs/rc_labs/scratch_tmp', None, 0)
        report = self.sync_with_quotas([quota])
        self.assertNotIn('/ifs/rc_labs/scratch_tmp', report['no_limit'])

    def test_group_without_matching_project_is_reported(self):
        quota = make_mock_quota('/ifs/rc_labs/ghost_lab', TIB, 0)
        report = self.sync_with_quotas([quota], group_name='ghost_lab')
        self.assertIn('ghost_lab', report['missing_projects'])
        self.assertEqual(Allocation.objects.count(), 0)

    def test_new_allocation_created_when_none_exists(self):
        quota = make_mock_quota('/ifs/rc_labs/poisson_lab', TIB, TIB // 2)
        report = self.sync_with_quotas([quota])

        self.assertIn('rc_labs/poisson_lab', report['created'])
        allocation = Allocation.objects.get(project=self.project)
        self.assertEqual(allocation.status.name, 'Active')
        self.assertEqual(allocation.path, 'rc_labs/poisson_lab')
        self.assertEqual(
            int(float(allocation.get_attribute('Quota_In_Bytes', typed=False))), TIB
        )

    def test_existing_allocation_is_updated_not_duplicated(self):
        allocation = AllocationFactory(project=self.project, status__name='Active')
        allocation.resources.add(self.resource)
        AllocationAttributeFactory(
            allocation=allocation, allocation_attribute_type=self.subdir_type, value='rc_labs/poisson_lab',
        )

        quota = make_mock_quota('/ifs/rc_labs/poisson_lab', TIB, TIB // 4)
        report = self.sync_with_quotas([quota])

        self.assertIn('rc_labs/poisson_lab', report['updated'])
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

        quota = make_mock_quota('/ifs/rc_labs/poisson_lab', TIB, TIB // 2)
        report = self.sync_with_quotas([quota])

        self.assertIn('rc_labs/poisson_lab', report['activated'])
        self.assertEqual(Allocation.objects.filter(project=self.project).count(), 1)
        pending.refresh_from_db()
        self.assertEqual(pending.status.name, 'Active')
        self.assertEqual(pending.path, 'rc_labs/poisson_lab')

    def test_pending_request_on_tier_resource_is_activated_and_repointed(self):
        tier_resource = ResourceFactory(name='Tier 1', resource_type__name='Storage Tier')
        self.resource.parent_resource = tier_resource
        self.resource.save()

        pending = AllocationFactory(
            project=self.project, status__name='New', justification='requesting tier 1 storage',
        )
        pending.resources.add(tier_resource)
        AllocationAttributeFactory(
            allocation=pending, allocation_attribute_type=self.quota_tib_type, value=1.0,
        )

        quota = make_mock_quota('/ifs/rc_labs/poisson_lab', TIB, TIB // 2)
        report = self.sync_with_quotas([quota])

        self.assertIn('rc_labs/poisson_lab', report['activated'])
        self.assertEqual(Allocation.objects.filter(project=self.project).count(), 1)
        pending.refresh_from_db()
        self.assertEqual(pending.status.name, 'Active')
        self.assertEqual(pending.path, 'rc_labs/poisson_lab')
        self.assertEqual(list(pending.resources.all()), [self.resource])

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

    def test_is_isilon_path_ignored(self):
        self.assertFalse(is_isilon_path_ignored('/ifs/rc_labs/poisson_lab'))
        with override_settings(ISILON_PATH_IGNORE=['/ifs/rc_labs/poisson_lab']):
            self.assertTrue(is_isilon_path_ignored('/ifs/rc_labs/poisson_lab'))

