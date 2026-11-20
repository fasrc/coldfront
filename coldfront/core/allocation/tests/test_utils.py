from unittest.mock import MagicMock

from django.test import SimpleTestCase

from coldfront.core.allocation.utils import check_l3_tag


class CheckL3TagIsilonTests(SimpleTestCase):
    """Tests for the isilon rc_fasse_labs criterion of check_l3_tag in allocation/utils.py"""

    def make(self, path, mount, resource_name='isilon01'):
        allocation = MagicMock(path=path)
        allocation.project.title = 'poisson_lab'
        resource = MagicMock()
        resource.name = resource_name
        resource.get_attribute.return_value = mount
        return allocation, resource

    def test_check_l3_tag_fasse_in_path_returns_true(self):
        self.assertTrue(check_l3_tag(*self.make('rc_fasse_labs/poisson_lab', None)))

    def test_check_l3_tag_fasse_in_storage_mount_returns_true(self):
        self.assertTrue(check_l3_tag(*self.make('poisson_lab', '/ifs/rc_fasse_labs')))

    def test_check_l3_tag_fasse_in_neither_returns_false(self):
        self.assertFalse(check_l3_tag(*self.make('poisson_lab', '/ifs/rc_labs')))

    def test_check_l3_tag_fasse_mount_on_non_isilon_resource_returns_false(self):
        self.assertFalse(check_l3_tag(*self.make('poisson_lab', '/ifs/rc_fasse_labs', 'holylfs09/tier1')))
