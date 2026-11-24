from django.test import TestCase

from coldfront.core.test_helpers.utils import require_plugin

require_plugin('coldfront.plugins.fasrc')

from coldfront.core.test_helpers.factories import (
    AAttributeTypeFactory,
    AllocationAttributeFactory,
    AllocationAttributeTypeFactory,
    AllocationFactory,
    AllocationStatusChoiceFactory,
    PAttributeTypeFactory,
    ProjectAttributeFactory,
    ProjectAttributeTypeFactory,
    ProjectFactory,
    ProjectStatusChoiceFactory,
    UserFactory,
)
from sftocf.signals import starfish_set_zone_userparam, starfish_zone_created


class PushGlobusUuidToNewZoneTests(TestCase):
    """push_globus_uuid_to_new_zone reacts to sftocf's starfish_zone_created by
    re-sending the already-generic starfish_set_zone_userparam signal for any
    of the project's active allocations that have a Globus UUID attribute."""

    def setUp(self):
        ProjectStatusChoiceFactory(name='Active')
        AllocationStatusChoiceFactory(name='Active')
        pi = UserFactory()
        self.project = ProjectFactory(pi=pi, status__name='Active')
        self.allocation = AllocationFactory(project=self.project, status__name='Active')

        self._received = []

        def handler(sender, **kwargs):
            self._received.append(kwargs)

        self._handler = handler
        starfish_set_zone_userparam.connect(handler, weak=False)
        self.addCleanup(starfish_set_zone_userparam.disconnect, handler)

    def test_pushes_globus_uuid_for_allocation_with_one(self):
        globus_attr_type = AllocationAttributeTypeFactory(
            name='Globus UUID', attribute_type=AAttributeTypeFactory(name='Text')
        )
        AllocationAttributeFactory(
            allocation=self.allocation,
            allocation_attribute_type=globus_attr_type,
            value='the-uuid',
        )

        starfish_zone_created.send(
            sender=self.__class__, project=self.project, zone_id='zone-123'
        )

        self.assertEqual(len(self._received), 1)
        self.assertEqual(self._received[0]['zone_id'], 'zone-123')
        self.assertEqual(self._received[0]['param_name'], 'archive_globus_collection')
        self.assertEqual(self._received[0]['param_value'], 'the-uuid')

    def test_does_nothing_without_a_globus_uuid(self):
        starfish_zone_created.send(
            sender=self.__class__, project=self.project, zone_id='zone-123'
        )

        self.assertEqual(self._received, [])


class PushGlobusUuidOnApprovalTests(TestCase):
    """push_globus_uuid_on_approval reacts to the built-in post_save signal on
    AllocationAttribute, filtered to the 'Globus UUID' attribute type, instead
    of coldfront.core.allocation.views needing to know anything about this."""

    def setUp(self):
        ProjectStatusChoiceFactory(name='Active')
        AllocationStatusChoiceFactory(name='Active')
        pi = UserFactory()
        self.project = ProjectFactory(pi=pi, status__name='Active')
        self.allocation = AllocationFactory(project=self.project, status__name='Active')
        self.globus_attr_type = AllocationAttributeTypeFactory(
            name='Globus UUID', attribute_type=AAttributeTypeFactory(name='Text')
        )

        self._received = []

        def handler(sender, **kwargs):
            self._received.append(kwargs)

        starfish_set_zone_userparam.connect(handler, weak=False)
        self.addCleanup(starfish_set_zone_userparam.disconnect, handler)

    def test_pushes_when_project_already_has_a_zone(self):
        zone_attr_type = ProjectAttributeTypeFactory(
            name='Starfish Zone', attribute_type=PAttributeTypeFactory(name='Text')
        )
        ProjectAttributeFactory(
            project=self.project, proj_attr_type=zone_attr_type, value='42'
        )

        AllocationAttributeFactory(
            allocation=self.allocation,
            allocation_attribute_type=self.globus_attr_type,
            value='the-uuid',
        )

        self.assertEqual(len(self._received), 1)
        self.assertEqual(self._received[0]['zone_id'], '42')
        self.assertEqual(self._received[0]['param_name'], 'archive_globus_collection')
        self.assertEqual(self._received[0]['param_value'], 'the-uuid')

    def test_does_nothing_when_project_has_no_zone_yet(self):
        AllocationAttributeFactory(
            allocation=self.allocation,
            allocation_attribute_type=self.globus_attr_type,
            value='the-uuid',
        )

        self.assertEqual(self._received, [])

    def test_ignores_other_attribute_types(self):
        other_attr_type = AllocationAttributeTypeFactory(
            name='Subdirectory', attribute_type=AAttributeTypeFactory(name='Text')
        )
        zone_attr_type = ProjectAttributeTypeFactory(
            name='Starfish Zone', attribute_type=PAttributeTypeFactory(name='Text')
        )
        ProjectAttributeFactory(
            project=self.project, proj_attr_type=zone_attr_type, value='42'
        )

        AllocationAttributeFactory(
            allocation=self.allocation,
            allocation_attribute_type=other_attr_type,
            value='some/path',
        )

        self.assertEqual(self._received, [])
