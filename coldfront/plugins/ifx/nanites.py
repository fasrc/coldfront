# -*- coding: utf-8 -*-

'''
Nanites Person synchronization code

Created on  2021-06-21

@author: Aaron Kitzmiller <aaron_kitzmiller@harvard.edu>
@copyright: 2021 The Presidents and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''

import logging
from ifxuser.nanites import Nanite2User
from coldfront.core.project import Project, ProjectUser, ProjectUserRoleChoice


logger = logging.getLogger(__name__)


class Nanite2ColdfrontUser(Nanite2User):
    '''
    Process roles for regular users (should be deactivated) and PIs
    '''
    def setUpForRole(self, user, role):
        '''
        Ensure that regular users cannot login
        '''
        if role == 'coldfront_user':
            user.is_active = False
            user.save()
        if role == 'coldfront_pi':
            # Go through affiliations.  If PI or Lab Manager, set as Manager of corresponding project
            for ua in user.useraffiliation_set.filter(role__in=['pi', 'lab_manager']):
                lab = ua.organization
                if lab.org_tree == 'Research Computing AD' and lab.code:
                    # Find project name that matches Organization.code
                    try:
                        project = Project.objects.get(name=lab.code)
                        try:
                            project_user = ProjectUser.objects.get(user=user, project=project)
                        except ProjectUser.DoesNotExist:
                            project_user= ProjectUser(user=user, project=project)
                        project_user.role = ProjectUserRoleChoice.objects.get(name='Manager')
                        project_user.save()
                    except Project.DoesNotExist:
                        logger.info(f'No Project matches RC organization code {lab.code}')
