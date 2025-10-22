import logging
from django.db.models import Q

from coldfront.core.allocation.models import (Allocation,
                                              AllocationStatusChoice,
                                              AllocationUser,
                                              AllocationUserStatusChoice)
from coldfront.core.resource.models import Resource

logger = logging.getLogger(__name__)

def check_l3_tag(allocation, resource):
    """Check whether an allocation should be tagged as l3, and add the tag if so.
    Criteria for l3 tagging:
        Any allocation for a project named .*_l3
        Any allocation on a lustre resource, with path matching ^F/|/F/ (I think?)
        Any allocation on an isilon resource, with path matching rc_fasse_labs
        Any allocation on h-nfse-01p
    """
    if allocation.project.title.endswith('_l3'):
        return True
    if 'lfs' in resource.name.lower() and 'F/' in allocation.path:
        return True
    if 'isilon' in resource.name.lower() and 'rc_fasse_labs' in allocation.path:
        return True
    if 'h-nfse-01p' in resource.name.lower():
        return True
    return False

def get_or_create_allocation(project_obj, resource_obj):
    """Get or create an Allocation for the given Project and Resource."""
    created = False
    try:
        allocation = Allocation.objects.get(
            project=project_obj, resources=resource_obj
        )
    except Allocation.DoesNotExist:
        allocation = Allocation.objects.create(
            project=project_obj, status=AllocationStatusChoice.objects.get(name="Active")
        )
        allocation.resources.add(resource_obj)
        logger.info("Created new allocation entry for project %s with resource %s: %s",
            project_obj.title, resource_obj.name, allocation.pk
        )
        created = True
    return allocation, created

def set_allocation_user_status_to_error(allocation_user_pk):
    allocation_user_obj = AllocationUser.objects.get(pk=allocation_user_pk)
    error_status = AllocationUserStatusChoice.objects.get(name='Error')
    allocation_user_obj.status = error_status
    allocation_user_obj.save()


def generate_guauge_data_from_usage(name, value, usage):

    label = '%s: %.2f of %.2f' % (name, usage, value)

    try:
        percent = (usage/value)*100
    except ZeroDivisionError:
        percent = 100
    except ValueError:
        percent = 100

    if percent < 80:
        color = '#6da04b'
    elif 80 <= percent < 90:
        color = '#ffc72c'
    else:
        color = '#e56a54'

    usage_data = {
        'columns': [
            [label, percent],
        ],
        'type': 'gauge',
        'colors': {
            label: color
        }
    }

    return usage_data


def get_user_resources(user_obj):

    if user_obj.is_superuser:
        resources = Resource.objects.filter(is_allocatable=True)
    else:
        resources = Resource.objects.filter(
            Q(is_allocatable=True) &
            Q(is_available=True) &
            (Q(is_public=True) | Q(allowed_groups__in=user_obj.groups.all()) | Q(allowed_users__in=[user_obj,]))
        ).distinct()

    return resources


def test_allocation_function(allocation_pk):
    print('test_allocation_function', allocation_pk)
