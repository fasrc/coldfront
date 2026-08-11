"""List allocations on bos-isilon/holy-isilon whose historical status was Active at a given datetime."""
from datetime import datetime, timezone

from django.core.management.base import BaseCommand

from coldfront.core.allocation.models import Allocation

RESOURCE_NAMES = ['bos-isilon', 'holy-isilon']
TARGET_DATETIME = datetime(2026, 8, 3, 19, 39, 56, 829643, tzinfo=timezone.utc)


class Command(BaseCommand):
    help = 'List allocations on bos-isilon/holy-isilon that were Active as of a given datetime'

    def handle(self, *args, **options):
        allocation_ids = Allocation.objects.filter(
            resources__name__in=RESOURCE_NAMES,
        ).values_list('id', flat=True).distinct()

        historical_allocations = Allocation.history.filter(
            id__in=list(allocation_ids),
        ).as_of(TARGET_DATETIME)

        active_allocations = [
            allocation for allocation in historical_allocations
            if allocation.status.name == 'Active'
        ]

        for allocation in active_allocations:
            self.stdout.write(
                f'{allocation.id}\t{allocation.project.title}\t{allocation.status.name}'
            )
        self.stdout.write(self.style.SUCCESS(
            f'{len(active_allocations)} active allocation(s) as of {TARGET_DATETIME.isoformat()}'
        ))
        return active_allocations
