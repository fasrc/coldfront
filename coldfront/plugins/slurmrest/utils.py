import logging
from slurmrest_python import SlurmApi, SlurmdbApi, ApiClient, Configuration
from coldfront.core.utils.common import import_from_settings


SLURMREST_CLUSTERS = import_from_settings('SLURMREST_CLUSTERS', {})
SLURMREST_NOOP = import_from_settings('SLURMREST_NOOP', False)

logger = logging.getLogger(__name__)


class SlurmError(Exception):
    pass


class SlurmApiConnection():

    def __init__(self, cluster_name):
        self.active_cluster = SLURMREST_CLUSTERS.get(cluster_name, None)
        assert self.active_cluster is not None, f"Unable to load cluster specs for {cluster_name} -- {SLURMREST_CLUSTERS}"
        self.configuration = self._return_configuration()
        self.slurm_api = self._return_apiconn(SlurmApi)
        self.slurmdb_api = self._return_apiconn(SlurmdbApi)

    def _return_configuration(self):
        configuration = Configuration(host=self.active_cluster.get('base_url'))
        configuration.api_key['token'] = self.active_cluster.get('token')
        return configuration

    def _return_apiconn(self, api):
        with ApiClient(self.configuration) as api_client:
            api_instance = api(api_client)
        return api_instance

    def _call_api(self, api_func, *, noop=False, **api_kwargs):
        """
        Helper that either calls `api_func`(**api_kwargs) or simulates it
        when noop is True.  It also handles error / warning logging.
        """
        if noop:
            api_kwargs['noop'] = True
            return api_kwargs

        try:
            response = api_func(api_kwargs)
        except Exception as exc:
            logger.exception("Exception when calling %s: %s", api_func.__name__, exc)
            raise

        if 'errors' in response:
            logger.exception("Errors from %s: %s", api_func.__name__, response['errors'])
        elif 'warnings' in response:
            logger.warning("Warnings from %s: %s", api_func.__name__, response['warnings'])

        return response


    # account methods
    def get_account(self, account_name, with_associations='true', with_coordinators='true'):
        account = self.slurmdb_api.slurmdb_v0041_get_single_account(
            account_name=account_name,
            with_associations=with_associations,
            with_coordinators=with_coordinators,
        )
        if account.errors:
            raise Exception('error/s found in get_account output: %s', account.errors)
        return account.to_dict()

    def get_accounts(self, with_associations='true', with_coordinators='true'):
        accounts = self.slurmdb_api.slurmdb_v0041_get_accounts(
            with_associations=with_associations,
            with_coordinators=with_coordinators,
        )
        if accounts.errors:
            raise Exception('error/s found in get_accounts output: %s', accounts.errors)
        return accounts.to_dict()

    def add_account(self, account_name, specs=None, noop=SLURMREST_NOOP):
        """Add a new account.
        account_name (str): name of the account to be added
        specs (list, default None): list of specifications for the account
        noop (bool, default False): if True, don't actually execute the action
        """
        if specs is None:
            specs = []
        account_dict = {
            'v0041_openapi_accounts_resp': {
                'accounts': {'name': account_name, 'specs': specs}
            }
        }
        response = self._call_api(
            self.slurmdb_api.slurmdb_v0041_post_accounts,
            noop=noop,
            **account_dict
        )
        logger.info('added accounts: %s', response)
        return response

    def remove_account(self, account_name, noop=SLURMREST_NOOP):
        """Remove an account.
        account_name (str): name of the account to be removed
        noop (bool, default False): if True, don't actually execute the action
        """
        response = self._call_api(
            self.slurmdb_api.slurmdb_v0041_delete_account,
            noop=noop,
            **{'account_name': account_name}
        )
        logger.info('removed account: %s', response)
        return response


    # association methods
    def get_assoc(self, *, user_name=None, account_name=None, assoc_id=None):
        if assoc_id:
            if user_name or account_name:
                raise ValueError("Either assoc_id OR user/account pair, not both.")
            args = {'id': assoc_id}
        else:
            if not (user_name and account_name):
                raise ValueError("Must supply assoc_id OR user_name/account_name.")
            args = {'user': user_name, 'account': account_name}
        associations = self.slurmdb_api.slurmdb_v0041_get_association(**args)
        return associations.to_dict()


    def add_assoc(self, account_name, user_name, noop=SLURMREST_NOOP):
        association_dict = {
            'v0041_openapi_assocs_resp': {
                'associations': {'account': account_name, 'user': user_name}
            }
        }
        response = self._call_api(
            self.slurmdb_api.slurmdb_v0041_post_associations,
            noop=noop,
            **association_dict
        )
        logger.info('added associations: %s', response)
        return response

    # def check_assoc(self, user, cluster, account):

    def remove_assoc(self, *, user_name=None, account_name=None, assoc_id=None, noop=SLURMREST_NOOP):
        """Remove association between a user and an account.
        Kwargs:
            user_name: name of user to be removed
            account_name: name of account from which to remove user
            assoc_id: id of the association to be deleted. Can be used instead of
                    the user_name/account_name lookup.
            noop (default False): if True, don't actually execute the action
        """
        if assoc_id:
            if user_name or account_name:
                raise ValueError("Either assoc_id OR user/account pair, not both.")
            args = {'id': assoc_id}
        else:
            if not (user_name and account_name):
                raise ValueError("Must supply assoc_id OR user_name/account_name.")
            args = {'user': user_name, 'account': account_name}

        response = self._call_api(
            self.slurmdb_api.slurmdb_v0041_delete_association,
            noop=noop,
            **args
        )
        logger.info("deleted associations: %s", response['removed_associations'])
        return response

    # cluster methods
    def get_clusters(self):
        clusters = self.slurmdb_api.slurmdb_v0041_get_clusters()
        if clusters.errors:
            raise Exception('error/s found in get_clusters output: %s', clusters.errors)
        return clusters.to_dict()

    # license methods
    def get_licenses(self):
        licenses = self.slurmdb_api.slurmdb_v0041_get_licenses()
        if licenses.errors:
            raise Exception('error/s found in get_licenses output: %s', licenses.errors)
        return licenses.to_dict()

    # node methods
    def get_node(self, node_name):
        node = self.slurm_api.slurm_v0041_get_node(node_name=node_name)
        if node.errors:
            raise Exception('error/s found in get_node output: %s', node.errors)
        return node.to_dict()

    def get_nodes(self, update_time=None, flags=None):
        nodes = self.slurm_api.slurm_v0041_get_nodes(update_time=update_time, flags=flags)
        if nodes.errors:
            raise Exception('error/s found in get_nodes output: %s', nodes.errors)
        return nodes.to_dict()


    # partition methods
    def get_partitions(self, update_time=None, flags=None):
        partitions = self.slurm_api.slurm_v0041_get_partitions(update_time=update_time, flags=flags)
        return partitions.to_dict()


    # user methods
    def get_user(self, user_name):
        user = self.slurmdb_api.slurmdb_v0041_get_user(user_name=user_name)
        if user.errors:
            raise Exception('error/s found in get_user output: %s', user.errors)
        return user.to_dict()

    def get_users(self):
        users = self.slurmdb_api.slurmdb_v0041_get_users()
        if users.errors:
            raise Exception('error/s found in get_users output: %s', users.errors)
        return users.to_dict()


    # qos methods
    def get_qos_list(self):
        """Get the list of QoS (Quality of Service) entries."""
        qos_list = self.slurmdb_api.slurmdb_v0041_get_qos()
        if qos_list.errors:
            raise Exception('error/s found in get_qos_list output: %s', qos_list.errors)
        return qos_list.to_dict()

    def get_qos(self, qos_name):
        """Get QoS entry by name."""
        qos = self.slurmdb_api.slurmdb_v0041_get_single_qos(qos_name=qos_name)
        if qos.errors:
            raise Exception('error/s found in get_qos output: %s', qos.errors)
        return qos.to_dict()

    def add_or_update_qos(self, qos_name, specs=None, noop=SLURMREST_NOOP):
        """Add or update a QoS entry.
        qos_name (str): name of the QoS to be added or updated
        specs (list, default None): list of specifications for the QoS
        noop (bool, default False): if True, don't actually execute the action
        """
        if specs is None:
            specs = []
        qos_dict = {
            'v0041_openapi_qos_resp': {
                'qos': {'name': qos_name, 'specs': specs}
            }
        }
        response = self._call_api(
            self.slurmdb_api.slurmdb_v0041_post_qos,
            noop=noop,
            **qos_dict
        )
        logger.info('added qos: %s', response)
        return response

    def remove_qos(self, qos_name, noop=SLURMREST_NOOP):
        response = self._call_api(
            self.slurmdb_api.slurmdb_v0041_delete_single_qos,
            noop=noop,
            **{'qos': qos_name}
        )
        logger.info('removed qos: %s', response)
        return response

    # share methods
    def get_shares(self, accounts=None, users=None):
        """Return share information.
        accounts (list, default None): accounts for which to get shares
        users (list, default None): users for which to get shares
        """
        shares = self.slurm_api.slurm_v0041_get_shares(accounts=accounts, users=users)
        if shares.errors:
            raise Exception('error/s found in get_shares output: %s', shares.errors)
        return shares.to_dict()
