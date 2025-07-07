import logging

from slurmrest_python_0_0_41 import SlurmApi, SlurmdbApi, ApiClient, Configuration

from coldfront.core.utils.common import import_from_settings

logger = logging.getLogger(__name__)

CLUSTERS = import_from_settings('CLUSTERS')

class SlurmApiConnection():

    def __init__(self, cluster_name):
        self.active_cluster = CLUSTERS.get(cluster_name, None)
        assert self.active_cluster is not None, f"Unable to load cluster specs for {cluster_name} -- {CLUSTERS}"
        self.configuration = self._return_configuration()
        self.slurm_api = self._return_apiconn(SlurmApi)
        self.slurmdb_api = self._return_apiconn(SlurmdbApi)

    def _return_configuration(self):
        configuration = Configuration(host=self.active_cluster.get('base_url'))
        configuration.api_key['token'] = self.active_cluster.get('user_token')
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

    def list_partitions(self, update_time=None, flags=None):
        return self.slurm_api.slurm_v0041_get_partitions(update_time=update_time, flags=flags)

    def remove_assoc(self, *, user_name=None, account_name=None, assoc_id=None, noop=False):
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

    def get_assoc(self, *, user_name=None, account_name=None, assoc_id=None):
        if assoc_id:
            if user_name or account_name:
                raise ValueError("Either assoc_id OR user/account pair, not both.")
            args = {'id': assoc_id}
        else:
            if not (user_name and account_name):
                raise ValueError("Must supply assoc_id OR user_name/account_name.")
            args = {'user': user_name, 'account': account_name}
        return self.slurmdb_api.slurmdb_v0041_get_association(**args)


    def add_assoc(self, account_name, user_name, noop=False):
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

    def get_shares(self, accounts=None, users=None):
        """Return share information.
        accounts (list, default None): accounts for which to get shares
        users (list, default None): users for which to get shares
        """
        return self.slurm_api.slurm_v0041_get_shares(accounts=accounts, users=users)
