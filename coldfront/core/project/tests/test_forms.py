import logging

from django.test import TestCase

from coldfront.core.project.forms import ProjectAddUsersToAllocationForm
from coldfront.core.test_helpers.factories import (
    setup_models,
    AllocationFactory,
    ResourceFactory,
)

logging.disable(logging.CRITICAL)

SELECT_ALL = ('__select_all__', 'Select All')


class ProjectAddUsersToAllocationFormTest(TestCase):
    """Tests for ProjectAddUsersToAllocationForm"""

    @classmethod
    def setUpTestData(cls):
        setup_models(cls)

    def add_cluster_allocation(self, name):
        resource = ResourceFactory(name=name, resource_type__name='Cluster')
        allocation = AllocationFactory(project=self.project, justification=f'{name} test')
        allocation.resources.add(resource)
        return allocation

    def get_choices(self):
        form = ProjectAddUsersToAllocationForm(self.pi_user, self.project.pk)
        return list(form.fields['allocation'].choices)

    def test_allocation_choices_single_allocation_omits_select_all(self):
        """With only one allocation, "Select All" is not offered."""
        choices = self.get_choices()
        self.assertEqual(len(choices), 1)
        self.assertNotIn(SELECT_ALL, choices)

    def test_allocation_choices_multiple_allocations_first_choice_is_select_all(self):
        """The template's JS treats allocation_0 as "Select All"; if a real
        allocation lands there, clicking it toggles every other checkbox."""
        self.add_cluster_allocation('another cluster')
        choices = self.get_choices()
        self.assertEqual(len(choices), 3)
        self.assertEqual(choices[0], SELECT_ALL)

    def test_allocation_choices_multiple_allocations_sorted_by_full_label(self):
        """Allocation choices after "Select All" are sorted case-insensitively by full label."""
        self.add_cluster_allocation('another cluster')
        self.add_cluster_allocation('Test Cluster B')
        labels = [label for _, label in self.get_choices()][1:]
        self.assertEqual(len(labels), 3)
        self.assertEqual(labels, sorted(labels, key=str.lower))
