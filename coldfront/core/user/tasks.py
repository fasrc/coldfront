import logging

from django_q.models import Schedule

from coldfront.core.project.models import Project
from coldfront.core.user.models import UserProfile

logger = logging.getLogger(__name__)

SCHEDULED_TASKS = [
    {'name': 'sync_userprofile_is_pi', 'schedule_type': Schedule.DAILY},
]

# A user is a PI if they are the PI of at least one project in one of these statuses.
PI_PROJECT_STATUSES = ('New', 'Active')


def sync_userprofile_is_pi():
    """Set UserProfile.is_pi to whether the user is the PI of any New or Active project.

    Returns:
        tuple[int, int]: the number of profiles set to is_pi=True and to is_pi=False.
    """
    pi_user_ids = Project.objects.filter(status__name__in=PI_PROJECT_STATUSES).values('pi_id')
    promoted = UserProfile.objects.filter(is_pi=False, user_id__in=pi_user_ids).update(is_pi=True)
    demoted = UserProfile.objects.filter(is_pi=True).exclude(user_id__in=pi_user_ids).update(is_pi=False)
    logger.info(
        'Synced UserProfile.is_pi: %s set True, %s set False.',
        promoted,
        demoted,
        extra={'category': 'task', 'status': 'success'},
    )
    return promoted, demoted
