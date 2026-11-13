import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from coldfront.core.utils.common import import_from_settings
from coldfront.plugins.ldap.utils import LDAPConn

logger = logging.getLogger(__name__)

LDAP_VENDOR_GROUP = import_from_settings('LDAP_VENDOR_GROUP', 'vendor_accounts')
LDAP_CENTER_STAFF_GROUPS = import_from_settings('LDAP_CENTER_STAFF_GROUPS', ['rc_accounts'])

EXTERNAL_GROUP_NAME = 'external'
VENDOR_GROUP_NAME = 'vendor'


class Command(BaseCommand):
    """
    Update ColdFront's external and vendor auth groups from AD
    """

    def handle(self, *args, **kwargs):
        """Add active AD users titled "EXTERNAL" to the external group, and sync the
        vendor group with AD vendor group membership."""
        ad_conn = LDAPConn()
        self.add_external_users(ad_conn)
        self.sync_vendor_users(ad_conn)

    def add_external_users(self, ad_conn):
        """Add enabled AD users with title "EXTERNAL" to the external group. Never removes anyone."""
        external_users = ad_conn.search_users(
            {'title': ['EXTERNAL'], 'userAccountControl': [512, 66048]},
            attributes=['sAMAccountName']
        )
        group = Group.objects.get(name=EXTERNAL_GROUP_NAME)
        users_to_add = get_user_model().objects.filter(
            username__in=[user['sAMAccountName'][0] for user in external_users]
        ).exclude(groups=group)
        for cf_user in users_to_add:
            cf_user.groups.add(group)
            logger.info("Added user %s to group %s", cf_user.username, EXTERNAL_GROUP_NAME)

    def sync_vendor_users(self, ad_conn):
        """Make the vendor group match AD: users in LDAP_VENDOR_GROUP or any group nested
        in it, except those in any LDAP_CENTER_STAFF_GROUPS group or any group nested in them.

        Users who qualify are added; everyone else in the vendor group is removed.
        """
        vendor_entries = ad_conn.search_nested_group_users(
            LDAP_VENDOR_GROUP,
            exclude_group_names=LDAP_CENTER_STAFF_GROUPS,
            attributes=['sAMAccountName'],
        )
        vendor_usernames = {entry['sAMAccountName'][0] for entry in vendor_entries}

        vendor_group = Group.objects.get(name=VENDOR_GROUP_NAME)
        users = get_user_model().objects
        for cf_user in users.filter(username__in=vendor_usernames).exclude(groups=vendor_group):
            cf_user.groups.add(vendor_group)
            logger.info("Added user %s to group %s", cf_user.username, VENDOR_GROUP_NAME)
        for cf_user in users.filter(groups=vendor_group).exclude(username__in=vendor_usernames):
            cf_user.groups.remove(vendor_group)
            logger.info("Removed user %s from group %s", cf_user.username, VENDOR_GROUP_NAME)
