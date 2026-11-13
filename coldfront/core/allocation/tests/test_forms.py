import logging

from django.test import TestCase

from coldfront.core.resource.models import Resource
from coldfront.core.allocation.forms import (
    AllocationApprovalForm,
    AllocationForm,
    HSPH_CODE,
    get_storage_creation_type,
)
from coldfront.core.test_helpers.factories import (
    setup_models,
    ResourceAttributeFactory,
    ResourceAttributeTypeFactory,
    ResourceFactory,
    ResourceTypeFactory,
)


logging.disable(logging.CRITICAL)

UTIL_FIXTURES = [
    "coldfront/core/test_helpers/test_data/test_fixtures/ifx.json",
]

class AllocationFormBaseTest(TestCase):
    """Base class for allocation view tests."""

    fixtures = UTIL_FIXTURES

    @classmethod
    def setUpTestData(cls):
        """Test Data setup for all allocation view tests."""
        setup_models(cls)

    def return_cleaned_form(self, FormClass):
        form = FormClass(
            data=self.post_data, request_user=self.pi_user, project_pk=self.project.pk
        )
        form.is_valid()
        form_cleaned = form.clean()
        return form_cleaned


class AllocationFormTest(AllocationFormBaseTest):
    """Tests for the AllocationCreateView"""

    def setUp(self):
        tier_restype = ResourceTypeFactory(name='Storage Tier')
        self.post_data = {
            'justification': 'test justification',
            'quantity': '1',
            'expense_code': '123-12312-3123-123123-123123-1231-23123',
            'resource': f'{self.storage_allocation.resources.first().pk}',
            'tier': Resource.objects.filter(resource_type=tier_restype).first()
        }

    def test_allocationform_expense_code_invalid1(self):
        """ensure correct error messages for incorrect expense_code value
        """
        self.post_data['expense_code'] = '123456789'
        form = AllocationForm(data=self.post_data, request_user=self.pi_user, project_pk=self.project.pk)
        self.assertEqual(
            form.errors['expense_code'], ['Input must contain exactly 33 digits.']
        )

    def test_allocationform_expense_code_invalid2(self):
        """ensure correct error messages for incorrect expense_code value
        """
        self.post_data['expense_code'] = '123-456AB-CDE789-22222-22222-22222-22222'
        form = AllocationForm(data=self.post_data, request_user=self.pi_user, project_pk=self.project.pk)
        self.assertEqual(
            form.errors['expense_code'], ["Input must consist only of digits (or x'es) and dashes."]
        )

    def test_allocationform_expense_code_invalid3(self):
        """ensure correct error messages for incorrect expense_code value
        """
        self.post_data['expense_code'] = '1Xx-' * 11
        form = AllocationForm(data=self.post_data, request_user=self.pi_user, project_pk=self.project.pk)
        self.assertEqual(
            form.errors['expense_code'], ["xes are only allowed in place of the product code (the third grouping of characters in the code)"]
        )

    def test_allocationform_expense_code_valid(self):
        """Test POST to the AllocationCreateView
        - ensure 33-digit codes go through
        - ensure correctly entered codes get properly formatted
        """
        # correct # of digits with no dashes
        cleaned_form = self.return_cleaned_form(AllocationForm)
        self.assertEqual(
            cleaned_form['expense_code'], '123-12312-8250-123123-123123-1231-23123'
        )

    def test_allocationform_expense_code_valid2(self):
        # check that expense_code was correctly formatted
        # correct # of digits with many dashes
        self.post_data['expense_code'] = '123-' * 11
        cleaned_form = self.return_cleaned_form(AllocationForm)

        self.assertEqual(
            cleaned_form['expense_code'], '123-12312-8250-123123-123123-1231-23123'
        )

    def test_allocationform_expense_code_valid3(self):
        """Test POST to the AllocationCreateView
        - ensure xes count as digits
        """
        # correct # of digits with no dashes
        self.post_data['expense_code'] = '123-12312-xxxx-123123-123123-1231-23123'
        cleaned_form = self.return_cleaned_form(AllocationForm)
        self.assertEqual(
            cleaned_form['expense_code'], '123-12312-8250-123123-123123-1231-23123'
        )

    def test_allocationform_expense_code_valid4(self):
        """Test POST to the AllocationCreateView
        - ensure xes count as digits
        """
        # correct # of digits with no dashes
        self.post_data['expense_code'] = '123.12312.xxxx.123123.123123.1231.23123'
        cleaned_form = self.return_cleaned_form(AllocationForm)
        self.assertEqual(
            cleaned_form['expense_code'], '123-12312-8250-123123-123123-1231-23123'
        )

    def test_allocationform_expense_code_multiplefield_invalid(self):
        """
        Test POST to AllocationCreateView in circumstance where code is entered
        and an existing_expense_codes value has also been selected
        """
        self.post_data['expense_code'] = '123-' * 11
        self.post_data['existing_expense_codes'] = HSPH_CODE
        form = AllocationForm(
            data=self.post_data, request_user=self.pi_user, project_pk=self.project.pk
        )
        self.assertIn("must either select an existing expense code or", form.errors['existing_expense_codes'][0])


class AllocationUpdateFormTest(AllocationFormBaseTest):
    """Tests for the AllocationNoteCreateView"""

    def setUp(self):
        self.post_data = {
            'resource': self.storage_allocation.resources.first(),
            'status': 'Active',
        }


class AllocationApprovalFormTest(TestCase):
    """Tests for AllocationApprovalForm's per-storage-type behavior."""

    @classmethod
    def setUpTestData(cls):
        tier_type = ResourceTypeFactory(name='Storage Tier')
        storage_type = ResourceTypeFactory(name='Storage')
        storage_type_attr = ResourceAttributeTypeFactory(name='storage_type')

        cls.powerscale_tier = ResourceFactory(name='Lab Storage', resource_type=tier_type)
        powerscale_vol = ResourceFactory(
            name='lab_storage', resource_type=storage_type, parent_resource=cls.powerscale_tier
        )
        ResourceAttributeFactory(
            resource=powerscale_vol, resource_attribute_type=storage_type_attr, value='powerscale'
        )
        cls.tape_tier = ResourceFactory(name='Tape', resource_type=tier_type)
        ResourceFactory(name='nesetape/tier3', resource_type=storage_type, parent_resource=cls.tape_tier)
        cls.ceph_tier = ResourceFactory(name='Tier 2', resource_type=tier_type)
        cls.ceph_vol = ResourceFactory(
            name='b-nfs02-p/tier2', resource_type=storage_type, parent_resource=cls.ceph_tier
        )
        cls.cluster = ResourceFactory(name='testcluster', resource_type=ResourceTypeFactory(name='Cluster'))

    def test_get_storage_creation_type_by_tier(self):
        self.assertEqual(get_storage_creation_type(self.powerscale_tier), 'powerscale')
        self.assertEqual(get_storage_creation_type(self.tape_tier), 'tape')
        self.assertEqual(get_storage_creation_type(self.ceph_tier), 'other')
        self.assertEqual(get_storage_creation_type(self.ceph_vol), 'other')
        self.assertIsNone(get_storage_creation_type(self.cluster))
        self.assertIsNone(get_storage_creation_type(None))

    def test_approval_form_powerscale_keeps_creation_options(self):
        form = AllocationApprovalForm(resource=self.powerscale_tier)
        self.assertFalse(form.manual_only)
        self.assertIn('auto_create_opts', form.fields)
        self.assertIn('sheetcheck', form.fields)
        self.assertIn('rc_labs/', form.fields['path'].label)

    def test_approval_form_powerscale_requires_creation_option(self):
        form = AllocationApprovalForm(data={}, resource=self.powerscale_tier)
        self.assertFalse(form.is_valid())
        self.assertIn('auto_create_opts', form.errors)

    def test_approval_form_manual_only_hides_creation_options(self):
        for tier in (self.tape_tier, self.ceph_tier):
            form = AllocationApprovalForm(resource=tier)
            self.assertTrue(form.manual_only)
            self.assertNotIn('auto_create_opts', form.fields)
            self.assertNotIn('sheetcheck', form.fields)
            self.assertTrue(form.fields['path'].required)

    def test_approval_form_manual_only_example_path_matches_storage_type(self):
        self.assertIn('hugljharvard', AllocationApprovalForm(resource=self.tape_tier).fields['path'].label)
        ceph_label = AllocationApprovalForm(resource=self.ceph_tier).fields['path'].label
        self.assertNotIn('<code>', ceph_label)

    def test_approval_form_manual_only_missing_path_invalid(self):
        form = AllocationApprovalForm(data={}, resource=self.tape_tier)
        self.assertFalse(form.is_valid())
        self.assertIn('path', form.errors)

    def test_approval_form_manual_only_with_path_sets_manual_choice(self):
        form = AllocationApprovalForm(data={'path': 'example/path'}, resource=self.ceph_tier)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['auto_create_opts'], '1')
        self.assertEqual(form.cleaned_data['path'], 'example/path')

    def test_approval_form_globus_uuid_only_for_tape(self):
        self.assertIn('globus_uuid', AllocationApprovalForm(resource=self.tape_tier).fields)
        for resource in (self.powerscale_tier, self.ceph_tier, self.cluster):
            self.assertNotIn('globus_uuid', AllocationApprovalForm(resource=resource).fields)

    def test_approval_form_tape_missing_globus_uuid_invalid(self):
        form = AllocationApprovalForm(data={'path': 'hugljharvard'}, resource=self.tape_tier)
        self.assertFalse(form.is_valid())
        self.assertIn('globus_uuid', form.errors)

    def test_approval_form_tape_malformed_globus_uuid_invalid(self):
        form = AllocationApprovalForm(
            data={'path': 'hugljharvard', 'globus_uuid': 'not-a-uuid'}, resource=self.tape_tier
        )
        self.assertFalse(form.is_valid())
        self.assertIn('globus_uuid', form.errors)

    def test_approval_form_tape_with_path_and_globus_uuid_valid(self):
        globus_uuid = '123e4567-e89b-12d3-a456-426614174000'
        form = AllocationApprovalForm(
            data={'path': 'hugljharvard', 'globus_uuid': globus_uuid}, resource=self.tape_tier
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['auto_create_opts'], '1')
        self.assertEqual(str(form.cleaned_data['globus_uuid']), globus_uuid)

    def test_approval_form_non_storage_unchanged(self):
        form = AllocationApprovalForm(resource=self.cluster)
        self.assertFalse(form.manual_only)
        self.assertIn('auto_create_opts', form.fields)
