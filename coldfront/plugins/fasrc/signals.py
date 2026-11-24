"""FASRC-specific signal receivers.

Organization-specific logic lives here, not in the generic plugins
(sftocf, isilon, ...) those plugins stay reusable by other institutions.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from coldfront.core.allocation.models import AllocationAttribute
from sftocf.signals import starfish_set_zone_userparam, starfish_zone_created

logger = logging.getLogger(__name__)


def _push_archive_globus_collection(allocation, globus_uuid):
    zone_id = allocation.project.sf_zone
    if not zone_id:
        logger.warning(
            'Project has no Starfish zone yet; archive_globus_collection will be '
            'pushed once update_zones creates one. project=%s allocation_pk=%s',
            allocation.project.title, allocation.pk
        )
        return
    starfish_set_zone_userparam.send(
        sender=allocation.__class__,
        zone_id=zone_id,
        param_name='archive_globus_collection',
        param_value=globus_uuid,
    )


@receiver(post_save, sender=AllocationAttribute)
def push_globus_uuid_on_approval(sender, instance, created, **kwargs):
    """When a Globus UUID attribute is set on an allocation, push it to the
    allocation's project's Starfish zone as archive_globus_collection.

    If the project has no zone yet, this is skipped; push_globus_uuid_to_new_zone
    below catches it up once update_zones creates one.
    """
    if not created or instance.allocation_attribute_type.name != 'Globus UUID':
        return
    _push_archive_globus_collection(instance.allocation, instance.value)


@receiver(starfish_zone_created)
def push_globus_uuid_to_new_zone(sender, **kwargs):
    """Catch up archive_globus_collection on a project's newly created zone.

    push_globus_uuid_on_approval above pushes it immediately when a project
    already has a Starfish zone; when it doesn't yet, this catches up for any
    of the project's active allocations that have a Globus UUID, once
    update_zones creates the zone.
    """
    project = kwargs['project']
    for allocation in project.allocation_set.filter(status__name='Active'):
        globus_uuid = allocation.get_attribute('Globus UUID')
        if not globus_uuid:
            continue
        _push_archive_globus_collection(allocation, globus_uuid)
