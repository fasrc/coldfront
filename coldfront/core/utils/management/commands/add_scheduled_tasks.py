import importlib

from django.apps import apps
from django.core.management.base import BaseCommand
from django.utils import timezone
from django_q.models import Schedule
from django_q.tasks import schedule


class Command(BaseCommand):
    help = 'Register scheduled tasks declared by installed apps'

    def handle(self, *args, **options):
        already_scheduled = set(Schedule.objects.values_list('func', flat=True))

        for app_config in apps.get_app_configs():
            if not app_config.name.startswith('coldfront'):
                continue
            try:
                tasks_module = importlib.import_module(f'{app_config.name}.tasks')
            except ModuleNotFoundError:
                continue
            for task in getattr(tasks_module, 'SCHEDULED_TASKS', []):
                self.register_task(app_config.name, task, already_scheduled)

    def register_task(self, app_name, task, already_scheduled):
        func = f"{app_name}.tasks.{task['name']}"
        if func in already_scheduled:
            return
        schedule(
            func,
            *task.get('args', ()),
            name=task['name'],
            schedule_type=task['schedule_type'],
            next_run=self._next_run(task.get('time')),
            cron=task.get('cron'),
            repeats=task.get('repeats', -1),
            **task.get('kwargs', {}),
        )

    def _next_run(self, time_str):
        run = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if time_str:
            hour, minute = (int(part) for part in time_str.split(':'))
            run = run.replace(hour=hour, minute=minute)
        return run
