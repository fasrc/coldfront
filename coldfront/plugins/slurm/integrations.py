import shlex
import struct
import subprocess
import logging
import json
import requests
import csv
from io import StringIO

from coldfront.core.utils.common import import_from_settings

logger = logging.getLogger(__name__)
SLURM_SACCTMGR_PATH = import_from_settings('SLURM_SACCTMGR_PATH', '/usr/bin/sacctmgr')
SLURM_SSHARE_PATH = import_from_settings('SLURM_SSHARE_PATH', '/usr/bin/sshare')
SLURM_SREPORT_PATH = import_from_settings('SLURM_SREPORT_PATH', '/usr/bin/sreport')
SLURM_SCONTROL_PATH = import_from_settings('SLURM_SCONTROL_PATH', '/usr/bin/scontrol')


class SlurmError(Exception):
    pass


class SlurmConnection:
    """Abstract base class for Slurm connections."""

    def __init__(self, cluster_name):
        """
        Initialize by reading available clusters from environment variables.
        """
        self.clusters = import_from_settings('CLUSTERS')
        self.active_cluster = self.clusters.get(cluster_name, None)
        assert self.active_cluster is not None, f"Unable to load cluster specs for {cluster_name} -- {self.clusters}"

    def list_partitions(self, noop=False):
        """List partitions."""
        raise NotImplementedError("Must be implemented in subclasses.")

    def remove_assoc(self, user, account, noop=False):
        """Remove an association."""
        raise NotImplementedError("Must be implemented in subclasses.")

    def remove_qos(self, user, account, qos, noop=False):
        """Remove a QoS from an association."""
        raise NotImplementedError("Must be implemented in subclasses.")

    def update_raw_share(self, user, account, raw_share, noop=False):
        """Update raw share for a user and account."""
        raise NotImplementedError("Must be implemented in subclasses.")

    def update_account_raw_share(self, account, raw_share, noop=False):
        """Update raw share for an account."""
        raise NotImplementedError("Must be implemented in subclasses.")

    def remove_account(self, account, noop=False):
        """Remove an account."""
        raise NotImplementedError("Must be implemented in subclasses.")

    def add_assoc(self, user, account, specs=None, noop=False):
        """Add an association."""
        raise NotImplementedError("Must be implemented in subclasses.")

    def add_account(self, account, specs=None, noop=False):
        """Add an account."""
        raise NotImplementedError("Must be implemented in subclasses.")

    def block_account(self, account, noop=False):
        """Block an account."""
        raise NotImplementedError("Must be implemented in subclasses.")

    def check_assoc(self, user, account):
        """Check if an association exists."""
        raise NotImplementedError("Must be implemented in subclasses.")

    def dump_cluster(self, file_name, noop=False):
        """Dump cluster data to a file."""
        raise NotImplementedError("Must be implemented in subclasses.")

    def collect_usage(self, output_file=None):
        """Collect usage data for accounts."""
        raise NotImplementedError("Must be implemented in subclasses.")

    def collect_shares(self, output_file=None):
        """Collect fairshare data for accounts."""
        raise NotImplementedError("Must be implemented in subclasses.")

    def slurm_fixed_width_lines_to_dict(self, line_iterable):
        """Take a list of fixed-width lines and convert them to dictionaries.
        line_iterable's first item should be the header; second item, dashed width indicators.
        """
        def convert_to_dict(input_list):
            keys = input_list[0]
            data = input_list[2:]
            result = []
            for item in data:
                result.append(dict(zip(keys, item)))
            return result

        widths = [n.count('-') + 1 for n in line_iterable[1].split()]
        fmtstring = ' '.join(f'{abs(fw)}s' for fw in widths)
        unpack = struct.Struct(fmtstring).unpack_from
        parse = lambda line: tuple(s.decode().strip() for s in unpack(line.encode()))
        # split each line by width
        line_iterable = [parse(line) for line in line_iterable if line]
        # pair values with headers
        return convert_to_dict(line_iterable)


class SlurmCliConnection(SlurmConnection):

    def __init__(self, cluster_name):
        super().__init__(cluster_name)
        command_path = self.active_cluster.get('path', '/usr/bin/')
        self.SSHARE = f"{command_path}sshare"
        self.SREPORT = f"{command_path}sreport"
        self.SACCTMGR = f"{command_path}sacctmgr"
        self.SCONTROL = f"{command_path}scontrol"

    def get_ssh_creds(self):
        return self.active_cluster.get('ssh_key'), self.active_cluster.get('user'), self.active_cluster.get('host')

    def get_ssh_command(self):
        ssh_key, user, host = self.get_ssh_creds()
        return f"ssh -o StrictHostKeyChecking=no -i {ssh_key} {user}@{host}"

    def _run_slurm_cmd(self, cmd, noop=True, show_output=False):
        if noop:
            logger.warning('NOOP - Slurm cmd: %s', cmd)
            return

        ssh_command = self.get_ssh_command()
        command = f"{ssh_command} '{' '.join(shlex.split(cmd))}'"
        logger.debug(f'Running slurm command: {command}')
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = process.communicate()
            if process.returncode != 0:
                stdout_str = stdout.decode('utf-8')
                if 'Nothing deleted' in stdout_str:
                    logger.warning(f'Nothing to delete: {cmd}')
                    return stdout
                if 'Nothing new added' in stdout_str:
                    logger.warning(f'Nothing new to add: {cmd}')
                    return stdout

                logger.error(f'Slurm command {cmd} failed: {cmd}')
                err_msg = f'return_value={process.returncode} stdout={stdout_str} stderr={stderr.decode("utf-8")}'
                logger.error(f'\x1b[33;20m Slurm cmd: \x1b[31;1m {command} \x1b[0m')
                raise SlurmError(err_msg)
            logger.debug(f'\x1b[33;20m Slurm cmd: \x1b[31;1m {command} \x1b[0m')
            if show_output:
                logger.debug(f'\x1b[33;20m Slurm cmd output: \x1b[31;1m {stdout} \x1b[0m')
            return stdout
        except Exception as e:
            raise SlurmError(f'Execution error: {e} for command {command}')

    def list_partitions(self, noop=False):
        cmd = f"{self.SCONTROL} show partitions"
        partitions = self._run_slurm_cmd(cmd, noop=noop)
        partitions = partitions.decode('utf-8').split('\n\n')
        partitions = [element.replace('\n ', '').replace('  ', ' ') for element in partitions]
        partitions = [element.split(' ') for element in partitions]
        partitions = [element for element in partitions if element != ['']]
        partitions = [
            {item.split('=')[0]: item.split('=')[1] for item in fields if '=' in item}
            for fields in partitions
        ]
        return partitions

    def remove_assoc(self, user, account, noop=False):
        cmd = f"{self.SACCTMGR} -Q -i delete user where name={user} account={account}"
        self._run_slurm_cmd(cmd, noop=noop)

    def remove_qos(self, user, account, qos, noop=False):
        cmd = f"{self.SACCTMGR} -Q -i modify user where name={user} account={account} set {qos}"
        self._run_slurm_cmd(cmd, noop=noop)

    def update_raw_share(self, user, account, raw_share, noop=False):
        cmd = f"{self.SACCTMGR} -Q -i modify user set fairshare={raw_share} where name={user} account={account}"
        return self._run_slurm_cmd(cmd, noop=noop)

    def update_account_raw_share(self, account, raw_share, noop=False):
        cmd = f"{self.SACCTMGR} -Q -i modify account set fairshare={raw_share} where name={account}"
        return self._run_slurm_cmd(cmd, noop=noop)

    def remove_account(self, account, noop=False):
        cmd = f"{self.SACCTMGR} -Q -i delete account where name={account}"
        self._run_slurm_cmd(cmd, noop=noop)

    def add_assoc(self, user, account, specs=None, noop=False):
        specs = specs or []
        cmd = f"{self.SACCTMGR} -Q -i create user name={user} account={account}"
        if specs:
            cmd += ' ' + ' '.join(specs)
        self._run_slurm_cmd(cmd, noop=noop)

    def add_account(self, account, specs=None, noop=False):
        specs = specs or []
        cmd = f"{self.SACCTMGR} -Q -i create account name={account}"
        if specs:
            cmd += ' ' + ' '.join(specs)
        self._run_slurm_cmd(cmd, noop=noop)

    def block_account(self, account, noop=False):
        cmd = f"{self.SACCTMGR} -Q -i modify account {account} set GrpSubmitJobs=0"
        self._run_slurm_cmd(cmd, noop=noop)

    def check_assoc(self, user, account):
        cmd = f"{self.SACCTMGR} list associations User={user} Account={account} Format=Account,User,QOS -P"
        output = self._run_slurm_cmd(cmd, noop=False)

        with StringIO(output.decode("UTF-8")) as fh:
            reader = csv.DictReader(fh, delimiter='|')
            for row in reader:
                if row['User'] == user and row['Account'] == account:
                    return True

        return False

    def dump_cluster(self, file_name, noop=False):
        def create_temp_dir(file_dir, ssh_key, user, host):
            subprocess.run([
                "ssh", "-o", "StrictHostKeyChecking=no", "-i", ssh_key,
                f"{user}@{host}", f"mkdir -p {file_dir}"
            ])

        temp_dir = file_name.split('cluster.cfg')[0]
        ssh_key, user, host = self.get_ssh_creds()
        create_temp_dir(temp_dir, ssh_key, user, host)

        cmd = f"{self.SACCTMGR} dump {self.active_cluster.get('name')} file={file_name}"
        self._run_slurm_cmd(cmd, noop=noop)
        copy_file_cmd = f"scp -o StrictHostKeyChecking=no -i {ssh_key} {user}@{host}:{file_name} {file_name}"
        process = subprocess.Popen(
            copy_file_cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate()
        assert process.returncode == 0, f'SCP error: {stderr} for command {copy_file_cmd}'

    def collect_usage(self, output_file=None):
        output_str = f'> {output_file}' if output_file else ''
        cmd = f"{self.SREPORT} -T gres/gpu,cpu accountutilization format='Account%25,Login%25,TRESname,Used' start=now-7days -t hours {output_str}"
        usage_data = self._run_slurm_cmd(cmd)
        return usage_data.decode('utf-8')

    def collect_shares(self, output_file=None):
        output_str = f'> {output_file}' if output_file else ''
        cmd = f"{self.SSHARE} -a -o 'Account%25,User%25,RawShares,NormShares,RawUsage,EffectvUsage,FairShare' {output_str}"
        share_data = self._run_slurm_cmd(cmd, noop=False)
        share_data = share_data.decode('utf-8').split('\n')
        if "-----" not in share_data[1]:
            share_data = share_data[1:]
        share_data = self.slurm_fixed_width_lines_to_dict(share_data)
        return share_data


class SlurmApiConnection(SlurmConnection):

    def __init__(self, cluster_name):
        super().__init__(cluster_name)
        self.base_url = self.active_cluster.get('base_url')

    def _make_request(self, endpoint, method="GET", data=None, use_slurmdb=False):
        """Perform an API call to the Slurm REST API."""
        url = f"{self.base_url}{endpoint}"
        if use_slurmdb is True: # Some endpoints are like /slurmdb/v0.0.42/accounts/ https://slurm.schedmd.com/rest_api.html
            url = url.replace('/slurm/', '/slurmdb/')
        headers = {
            'Content-Type': 'application/json',
            'X-SLURM-USER-NAME': self.active_cluster.get('user_name'),
            'X-SLURM-USER-TOKEN': self.active_cluster.get('user_token')
        }
        try:
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=10)
            elif method == "POST":
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == "PUT":
                response = requests.put(url, json=data, headers=headers, timeout=10)
            elif method == "DELETE":
                response = requests.delete(url, headers=headers, timeout=10)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            response.raise_for_status()
            logger.debug(f"API Request to {url} succeeded with status {response.status_code}")
            return response.json()
        except requests.RequestException as e:
            logger.error(f"API Request to {url} failed: {str(e)}")
            raise SlurmError(f"API request failed: {str(e)}")

    def list_partitions(self, noop=False):
        return self._make_request("/partitions")

    def remove_assoc(self, user, account, noop=False):
        data = {"user": user, "account": account}
        return self._make_request(f"/assoc/{user}/{account}", method="DELETE", data=data)

    def remove_qos(self, user, account, qos, noop=False):
        data = {"user": user, "account": account, "qos": qos}
        return self._make_request(f"/qos/{user}/{account}/{qos}", method="DELETE", data=data)

    def update_raw_share(self, user, account, raw_share, noop=False):
        data = {"fairshare": raw_share}
        return self._make_request(f"/assoc/{user}/{account}", method="PUT", data=data)

    def update_account_raw_share(self, account, raw_share, noop=False):
        data = {"fairshare": raw_share}
        return self._make_request(f"/account/{account}", method="PUT", data=data)

    def remove_account(self, account, noop=False):
        return self._make_request(f"/account/{account}", method="DELETE")

    def add_assoc(self, user, account, specs=None, noop=False):
        data = {
            "user": user,
            "account": account,
            "specs": specs or []
        }
        return self._make_request("/assoc", method="POST", data=data)

    def add_account(self, account, specs=None, noop=False):
        data = {
            "account": account,
            "specs": specs or []
        }
        return self._make_request("/account", method="POST", data=data)

    def block_account(self, account, noop=False):
        data = {"GrpSubmitJobs": 0}
        return self._make_request(f"/account/{account}", method="PUT", data=data)

    def check_assoc(self, user, account, noop=False):
        response = self._make_request(f"/assoc/{user}/{account}")
        return response.get("exists", False)

    def dump_cluster(self, file_name, noop=False):
        data = []
        try:
            # Get a list of all accounts
            accounts_response = self._make_request("/accounts", use_slurmdb=True)
            account_names = [account['name'] for account in accounts_response['accounts']]
            for account in account_names:
                # Get all users for each account
                users_response = self._make_request(f"/associations/{account['name']}")
                users = users_response.json()
                for user in users:
                    user_data = {
                        "user": user['name'],
                        "account": account['name'],
                        "shares": user.get('shares', None),
                        "priority": user.get('priority', None),
                    }
                    data.append(user_data)
            if noop:
                print(data)
            else:
                with open(file_name, 'w') as f:
                    json.dump(data, f, indent=4)
                print(f"Cluster dump saved to {file_name}")

        except Exception as e:
            print(f"Error during dump_cluster: {e}")

    def collect_usage(self, output_file=None, noop=False):
        usage_data = self._make_request("/usage")
        if output_file:
            with open(output_file, 'w') as f:
                f.write(str(usage_data))
        return usage_data

    def collect_shares(self, output_file=None, noop=False):
        share_data = self._make_request("/shares")
        if output_file:
            with open(output_file, 'w') as f:
                f.write(str(share_data))
        return share_data


def get_cluster_connection(cluster_name):
    slurm_connection = SlurmConnection(cluster_name)
    if slurm_connection.active_cluster.get('type')=='cli':
        return SlurmCliConnection(cluster_name)
    if slurm_connection.active_cluster.get('type')=='api':
        return SlurmApiConnection(cluster_name)
