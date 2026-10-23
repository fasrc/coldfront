import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from coldfront.plugins.ldap.utils import LDAPConn

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    """
    Update ProjectUsers for active Projects using ADGroup and ADUser data
    """

    def handle(self, *args, **kwargs):
        """Identify active users with title "EXTERNAL" or "VENDOR" in AD and add them to 
        respective groups using IfxUserGroups model"""
        ad_conn = LDAPConn()
        external_users = ad_conn.search_users(
            {'title': ['EXTERNAL', 'VENDOR'], 'userAccountControl': [512, 66048]},
            attributes=['sAMAccountName', 'title']
        )
        coldfront_users = get_user_model().objects.filter(
                username__in=[user['sAMAccountName'][0] for user in external_users]
        )
        for ldap_user in external_users:
            username = ldap_user['sAMAccountName'][0]
            groupname = ldap_user['title'][0].lower()

            cf_user_search = coldfront_users.filter(username=username)
            if cf_user_search.exists():
                cf_user = cf_user_search.first()
                if not cf_user.groups.filter(name=groupname).exists():
                    group = Group.objects.get(name=groupname)
                    cf_user.groups.add(group)
                    logger.info("Added user %s to group %s", username, groupname)

