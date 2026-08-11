"""Integration tests for SlurmApiConnection against the real slurmrest_python SDK.

These tests do NOT mock slurmrest_python's SlurmApi/SlurmdbApi classes. They
build real instances of them, configured to talk to a closed local port, and
drive them through SlurmApiConnection's methods exactly as production code
does. Nothing about the SDK itself is faked: attribute lookups, keyword
argument names, and request-body shapes are all validated by the real,
installed slurmrest_python package before any network activity happens.

Every test asserts the same thing: that the call gets past the SDK and
reaches an actual (failed) network attempt, raising
`urllib3.exceptions.MaxRetryError` (connection refused -- the target port is
always closed, so this happens immediately, with no DNS lookup and no
dependency on network access in CI). That's the "correct" outcome. A call
that references a method the SDK doesn't have raises a real `AttributeError`
instead; a call with a wrong parameter name or shape raises a real pydantic
`ValidationError` instead -- either way the test fails, because those are
not MaxRetryError. There's no separate "documents a known bug" class: if
utils.py calls the SDK wrong, the corresponding test here just fails, with
the real SDK exception as the reason. An SDK upgrade that renames or removes
a method will make the relevant test fail the same way, without anyone
updating the test.
"""

import logging
from unittest import mock

from django.test import SimpleTestCase
from urllib3.exceptions import MaxRetryError
from slurmrest_python import ApiClient, Configuration, SlurmApi, SlurmdbApi

from coldfront.plugins.slurmrest.utils import SlurmApiConnection

# Guaranteed to refuse the connection immediately: loopback, no DNS lookup,
# and port 1 is never listening. Keeps these tests fast, deterministic, and
# offline.
_CLOSED_PORT_HOST = 'http://127.0.0.1:1'

# Every test below deliberately drives a real connection-refused error
# through urllib3's retry logic; silence its per-retry WARNING logging
# (emitted by the urllib3.connectionpool logger specifically) so test output
# isn't dominated by expected noise.
logging.getLogger('urllib3.connectionpool').setLevel(logging.ERROR)


def _build_connection():
    """Build a SlurmApiConnection wired to real (unmocked) SDK client objects."""
    configuration = Configuration(host=_CLOSED_PORT_HOST)
    configuration.api_key['token'] = 'test-token'
    with ApiClient(configuration) as api_client:
        slurmdb_api = SlurmdbApi(api_client)
        slurm_api = SlurmApi(api_client)

    conn = SlurmApiConnection.__new__(SlurmApiConnection)
    conn.active_cluster = {
        'name': 'test-cluster',
        'base_url': _CLOSED_PORT_HOST,
        'token': 'test-token',
    }
    conn.slurmdb_api = slurmdb_api
    conn.slurm_api = slurm_api
    return conn


class SlurmApiConnectionIntegrationTestCase(SimpleTestCase):

    def setUp(self):
        self.conn = _build_connection()

    def assertReachesRealSdkTransport(self, func, *args, **kwargs):
        """Assert `func` gets past real SDK attribute lookup and parameter
        validation and reaches the point of an actual network call.

        Proves the SDK method name and keyword arguments utils.py sends are
        valid against the installed slurmrest_python package, without a live
        Slurm server or a hand-maintained mock of the SDK's call signatures.
        """
        with self.assertRaises(MaxRetryError):
            func(*args, **kwargs)


class SdkCallsTests(SlurmApiConnectionIntegrationTestCase):
    """Every SlurmApiConnection method that calls into the SDK, asserting it
    reaches the real network transport. A method whose SDK call is wrong
    (bad method name, bad kwarg name, bad parameter shape) fails its test
    here directly, with the real SDK exception as the failure -- not a
    separate, always-green test asserting the bug persists.
    """

    def test_get_account(self):
        self.assertReachesRealSdkTransport(self.conn.get_account, 'acct1')

    def test_get_accounts(self):
        self.assertReachesRealSdkTransport(self.conn.get_accounts)

    def test_add_account(self):
        self.assertReachesRealSdkTransport(
            self.conn.add_account, 'newacct', specs=['MaxJobs=10']
        )

    def test_remove_account(self):
        self.assertReachesRealSdkTransport(self.conn.remove_account, 'acct1')

    def test_get_assocs(self):
        self.assertReachesRealSdkTransport(self.conn.get_assocs)

    def test_get_assoc_by_id(self):
        self.assertReachesRealSdkTransport(self.conn.get_assoc, assoc_id='5')

    def test_get_assoc_by_user_and_account(self):
        self.assertReachesRealSdkTransport(
            self.conn.get_assoc, user_name='bob', account_name='acct1'
        )

    def test_post_assoc(self):
        with mock.patch.object(
            self.conn, 'get_assoc',
            return_value={'associations': [{'user': 'bobtest', 'account': 'acct1'}]},
        ):
            self.assertReachesRealSdkTransport(
                self.conn.post_assoc, 'acct1', 'bobtest', {'shares_raw': 100}
            )

    def test_add_assoc(self):
        self.assertReachesRealSdkTransport(self.conn.add_assoc, 'acct1', 'bobtest')

    def test_remove_assoc_by_user_and_account(self):
        self.assertReachesRealSdkTransport(
            self.conn.remove_assoc, user_name='bobtest', account_name='acct1'
        )

    def test_remove_assoc_by_id(self):
        self.assertReachesRealSdkTransport(self.conn.remove_assoc, assoc_id=5)

    def test_get_config(self):
        self.assertReachesRealSdkTransport(self.conn.get_config)

    def test_get_clusters(self):
        self.assertReachesRealSdkTransport(self.conn.get_clusters)

    def test_get_licenses(self):
        self.assertReachesRealSdkTransport(self.conn.get_licenses)

    def test_get_node(self):
        self.assertReachesRealSdkTransport(self.conn.get_node, 'node1')

    def test_get_nodes(self):
        self.assertReachesRealSdkTransport(self.conn.get_nodes)

    def test_get_partitions(self):
        self.assertReachesRealSdkTransport(self.conn.get_partitions)

    def test_get_user(self):
        self.assertReachesRealSdkTransport(self.conn.get_user, 'alice')

    def test_get_users(self):
        self.assertReachesRealSdkTransport(self.conn.get_users)

    def test_update_user(self):
        with mock.patch.object(
            self.conn, 'get_user',
            return_value={'users': [{'name': 'alice', 'default_account': 'root'}]},
        ):
            self.assertReachesRealSdkTransport(
                self.conn.update_user, 'alice', {'default_account': 'physics'}
            )

    def test_get_qos_list(self):
        self.assertReachesRealSdkTransport(self.conn.get_qos_list)

    def test_get_qos(self):
        self.assertReachesRealSdkTransport(self.conn.get_qos, 'normal')

    def test_add_or_update_qos(self):
        self.assertReachesRealSdkTransport(
            self.conn.add_or_update_qos, 'general', specs=['MaxTRESPerUser=cpu=10']
        )

    def test_remove_qos(self):
        self.assertReachesRealSdkTransport(self.conn.remove_qos, 'general')

    def test_get_shares(self):
        self.assertReachesRealSdkTransport(self.conn.get_shares)

    def test_get_wckeys(self):
        self.assertReachesRealSdkTransport(self.conn.get_wckeys)
