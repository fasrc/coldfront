# SPDX-FileCopyrightText: (C) ColdFront Authors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import logging
import sys

from django.core.management.base import BaseCommand

from coldfront.core.resource.models import ResourceAttribute
from coldfront.core.utils.common import import_from_settings

from coldfront_plugin_slurmrest.config import SLURM_CLUSTER_ATTRIBUTE_NAME
from coldfront_plugin_slurmrest.utils import SlurmError, SlurmApiConnection

SLURM_IGNORE_USERS = import_from_settings("SLURM_IGNORE_USERS", [])
SLURM_IGNORE_ACCOUNTS = import_from_settings("SLURM_IGNORE_ACCOUNTS", [])
SLURM_IGNORE_CLUSTERS = import_from_settings("SLURM_IGNORE_CLUSTERS", [])
SLURM_NOOP = import_from_settings("SLURM_NOOP", False)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Check consistency between Slurm associations and ColdFront allocations. Optionally remove associations in Slurm that no longer exist in ColdFront."

    def add_arguments(self, parser):
        parser.add_argument(
            "-s", "--sync", help="Remove associations in Slurm that no longer exist in ColdFront", action="store_true"
        )
        parser.add_argument("-n", "--noop", help="Print commands only. Do not run any commands.", action="store_true")
        parser.add_argument("-c", "--cluster", help="Check specific cluster", default=None)
        parser.add_argument("-a", "--account", help="Check specific account")
        parser.add_argument("-u", "--username", help="Check specific username")

    def _skip_user(self, user, account):
        if user in SLURM_IGNORE_USERS:
            logger.debug("Ignoring user %s", user)
            return True

        if account in SLURM_IGNORE_ACCOUNTS:
            logger.debug("Ignoring account %s", account)
            return True

        if self.filter_account and account != self.filter_account:
            return True

        if self.filter_user and user != self.filter_user:
            return True

        return False

    def _skip_account(self, account):
        if account in SLURM_IGNORE_ACCOUNTS:
            logger.debug("Ignoring account %s", account)
            return True

        if self.filter_user:
            return True

        if self.filter_account and account != self.filter_account:
            return True

        return False


    def check_consistency(self, slurm_cluster, coldfront_resource):
        """Check for accounts in Slurm NOT in ColdFront"""
        cluster_account_response = slurm_cluster.get_accounts()
        cluster_accounts = cluster_account_response.get("accounts", {})
        resource_allocations = coldfront_resource.allocation_set.filter(status__name='Active')
        allocation_dict = {
            allocation.project.title: allocation for allocation in resource_allocations
        }

        for account in cluster_accounts:
            account_name = account['name']
            if account_name == "root" or self._skip_account(account):
                logger.debug("Ignoring account %s", account["name"])
                continue
            if account_name in allocation_dict:
                logger.debug("Slurm account %s found in ColdFront", account_name)
                allocation_users = allocation_dict[account_name].allocationuser_set.filter(
                        status__name='Active')
                for association in account.get("associations", []):
                    username = association['name']
                    if username == "root" or self._skip_user(username, account_name):
                        logger.debug("Ignoring user %s in account %s", username, account_name)
                        continue
                    if username in [au.user.username for au in allocation_users]:
                        logger.debug(
                            "Slurm user %s in account %s found in ColdFront", username, account_name
                        )
                        # TODO: check qos

                    else:
                        logger.warning(
                            "Slurm user %s has no association with account %s in ColdFront, removing association",
                            account_name, username,
                        )
                        slurm_cluster.remove_assoc(assoc_id=association['id'], noop=self.noop)
            else:
                for association in account.get("associations", []):
                    username = association['name']
                    if username == "root" or self._skip_user(username, account_name):
                        logger.debug("Ignoring user %s in account %s", username, account_name)
                        continue

                    logger.warning(
                        "Slurm account %s with user %s not found in ColdFront. Removing association.",
                        account_name, username,
                    )
                    slurm_cluster.remove_assoc(assoc_id=association['id'], noop=self.noop)
                slurm_cluster.remove_account(account_name, noop=self.noop)



    def handle(self, *args, **options):

        self.sync = False
        if options["sync"]:
            self.sync = True
            logger.warning("Syncing Slurm with ColdFront")

        self.noop = SLURM_NOOP
        if options["noop"]:
            self.noop = True
            logger.warning("NOOP enabled")

        # clusters
        clusters = import_from_settings("SLURMREST_CLUSTERS", default={})
        if options["cluster"]:
            if options["cluster"] in clusters:
                clusters = {options["cluster"]: clusters[options["cluster"]]}
            else:
                logger.error("Cluster %s not found in SLURMREST_CLUSTERS", options["cluster"])
                sys.exit(1)

        self.filter_user = options["username"]
        self.filter_account = options["account"]

        for cluster_name in clusters.keys():
            logger.info("Checking Slurm cluster %s", cluster_name)

            slurm_cluster = SlurmApiConnection(cluster_name)

            if cluster_name in SLURM_IGNORE_CLUSTERS:
                logger.warning("Ignoring cluster %s. Nothing to do.", cluster_name)
                sys.exit(0)

            try:
                coldfront_resource = ResourceAttribute.objects.get(
                    resource_attribute_type__name=SLURM_CLUSTER_ATTRIBUTE_NAME,
                    value=cluster_name
                ).resource
            except ResourceAttribute.DoesNotExist:
                logger.error(
                    "No Slurm '%s' cluster resource found in ColdFront using '%s' attribute",
                    cluster_name,
                    SLURM_CLUSTER_ATTRIBUTE_NAME,
                )
                continue

            self.check_consistency(slurm_cluster, coldfront_resource)
