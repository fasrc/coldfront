# -*- coding: utf-8 -*-

'''
Views
'''
import os
from datetime import datetime

import pandas as pd
from django.http import Http404
from django.shortcuts import render
from django.views.generic.base import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from coldfront.config.env import ENV
from coldfront.core.project.models import Project
from coldfront.core.allocation.models import Allocation

if ENV.bool('PLUGIN_SFTOCF', default=False):
    from coldfront.plugins.sftocf.utils import STARFISH_SERVER, StarFishServer

class MonitorView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    '''
    '''
    template_name = 'monitor.html'

    def test_func(self):
        '''UserPassesTestMixin Tests'''
        if self.request.user.is_superuser:
            return True
        raise Http404

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scan_data_processed = None
        if ENV.bool('PLUGIN_SFTOCF', default=False):

            sf = StarFishServer(STARFISH_SERVER)
            scan_data = sf.get_most_recent_scans()
            scan_data_processed = [
                        {'volume': s['volume'],
                         'state': s['state']['name'],
                         'creation_time_hum': s['creation_time_hum'],
                         'end_hum': s['end_hum'],
                         'duration_hum': s['duration_hum'],
                } for s in scan_data]

        # database checks
        projects = Project.objects.all()
        pi_not_projectuser = [p for p in projects if p.pi_id not in  p.projectuser_set.values_list('user_id', flat=True)]
        allocation_not_changeable = Allocation.objects.filter(is_changeable=False)

        # ui checks
        ui_error_file = 'local_data/error_checks.csv'
        page_issues_dt = None
        page_issues = None
        if os.path.isfile(ui_error_file):
            page_issues_ts = os.path.getmtime(ui_error_file)
            page_issues_dt = datetime.fromtimestamp(page_issues_ts)
            page_issues = pd.read_csv(ui_error_file).to_dict('records')

        context['scan_data'] = scan_data_processed
        context['page_issues_dt'] = page_issues_dt
        context['page_issues'] = page_issues
        context['pi_not_projectuser'] = pi_not_projectuser
        context['allocation_not_changeable'] = allocation_not_changeable

        return context