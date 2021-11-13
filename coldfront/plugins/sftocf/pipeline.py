import os
import re
import json
import time
import timeit
import logging
import requests
from pathlib import Path
from datetime import datetime

# from tqdm import tqdm
# from pynput import keyboard

from django_q.tasks import async_task
from django.contrib.auth import get_user_model
from coldfront.core.project.models import Project, ProjectUser
from coldfront.core.utils.common import import_from_settings
from coldfront.core.allocation.models import Allocation, AllocationUser

logger = logging.getLogger(__name__)
logger.propagate = False
logger.setLevel(logging.DEBUG)
filehandler = logging.FileHandler('coldfront/plugins/sftocf/sfc.log', 'w')
logger.addHandler(filehandler)


svp = {
"holysfdb01": {
    "holylfs04":"HDD/C/LABS",
    'holylfs05':"C/LABS",
    'holystore01':"C/LABS",
    },
"holysfdb02": {
    "boslfs02":"LABS",
    "bos-isilon":"rc_labs",
    "holy-isilon":"rc_labs",
    "holylfs02":"LABS",
  }
}


class StarFishServer:
    """
    """

    def __init__(self, server):
        self.name = server
        self.api_url = f"https://{server}.rc.fas.harvard.edu/api/"
        self.token = self.get_auth_token()
        self.headers = self.generate_headers()
        self.volumes = self.get_volume_names()

    def get_auth_token(self):
        """Obtain a token through the auth endpoint.
        """
        logger.debug("get_auth_token")
        username = import_from_settings('SFUSER')
        password = import_from_settings('SFPASS')
        auth_url = self.api_url + "auth/"
        todo = {"username": username, "password": password}
        response = requests.post(auth_url, json=todo)
        # response.status_code
        response_json = response.json()
        logger.debug(response_json)
        token = response_json["token"]
        logger.debug(token)
        return token

    def generate_headers(self):
        """Generate "headers" attribute by using the "token" attribute.
        """
        headers = {
            "accept": "application/json",
            "Authorization": "Bearer {}".format(self.token),
        }
        return headers

    # 2A. Generate list of volumes to search, along with top-level paths
    def get_volume_names(self):
        """ Generate a list of the volumes available on the server.
        """
        logger.debug("get_volume_names")
        vols_paths = {}
        stor_url = self.api_url + "storage/"
        response = return_get_json(stor_url, self.headers)
        volnames = [i["name"] for i in response["items"]]
        logger.debug("volnames:{}".format(volnames))
        return volnames

    def get_subpaths(self, volpath):
        """Generate list of directories in top layer of designated volpath.
        Parameters
        ----------
        volpath : string
            The volume and path.
        Returns
        -------
        subpaths : list of strings
        """
        logger.debug("get_subpaths")
        getsubpaths_url = self.api_url + "storage/" + volpath
        request = return_get_json(getsubpaths_url, self.headers)
        pathdicts = request["items"]
        subpaths = [i["Basename"] for i in pathdicts]
        logger.debug(subpaths)
        return subpaths

    def create_query(self, query, group_by, volpath, sec=3):
        """Produce a Query class object.
        Parameters
        ----------
        query : string
        group_by : string
        volpath : string
        sec : integer, optional
        Returns
        -------
        query : Query class object
        """
        query = StarFishQuery(
            self.headers, self.api_url, query, group_by, volpath, sec=sec
        )
        return query

    def get_vol_user_membership(self, volume):
        logger.debug("get_vol_user_membership")
        usermap_url = self.api_url + "mapping/user_membership?volume_name=" + volume
        userlist = return_get_json(usermap_url, self.headers)
        logger.debug(f"userlist:\n{userlist}")
        return userlist

    def get_vol_user_name_ids(self, volume):
        logger.debug("get_vol_user_name_ids")
        usermap_url = self.api_url + "mapping/user?volume_name=" + volume
        users = return_get_json(usermap_url, self.headers)
        userdict = {u["uid"]: u["name"] for u in users}
        logger.debug(f"userdict:\n{userdict}")
        return userdict

    def get_vol_group_membership(self, volume):
        logger.debug("get_vol_groups")
        group_url = self.api_url + "mapping/group_membership?volume_name=" + volume
        grouplist = return_get_json(group_url, self.headers)
        logger.debug(f"grouplist:\n{grouplist}")
        return grouplist


class StarFishQuery:
    def __init__(self, headers, api_url, query, group_by, volpath, sec=3):
        self.api_url = api_url
        self.headers = headers
        self.query_id = self.post_async_query(query, group_by, volpath)
        self.result = self.return_results_once_prepared(sec=sec)

    def post_async_query(self, query, group_by, volpath):
        logger.debug("post_async_query")
        query_url = self.api_url + "async/query/"

        params = {
            "volumes_and_paths": volpath,
            "queries": query,
            "format": "parent_path fn type size blck ct mt at uid gid mode",
            "sort_by": group_by,
            "group_by": group_by,
            "limit": "100000",
            "force_tag_inherit": "false",
            "output_format": "json",
            "delimiter": ",",
            "escape_paths": "false",
            "print_headers": "true",
            "size_unit": "B",
            "humanize_nested": "false",
            "mount_agent": "None",
        }
        r = requests.post(query_url, params=params, headers=self.headers)
        response = r.json()
        logger.debug(response)
        return response["query_id"]

    # 4. return query results
    def return_results_once_prepared(self, sec=3):
        logger.debug("return_results_once_prepared")
        # add a means of triggering query deletion
        while True:
            # delete_query = False
            # with keyboard.Listener(on_press=self.on_press) as listener:
            # while delete_query == False:
            query_check_url = self.api_url + "async/query/" + self.query_id
            response = return_get_json(query_check_url, self.headers)
            if response["is_done"] == True:
                result = self.return_query_result()
                return result
            else:
                time.sleep(sec)
                # listener.join()

    # def on_press(self, key):
    #     print (key)
    #     if key == keyboard.Key.end:
    #         print ('end pressed')
    #         delete_query = True
    #         return False

    def return_query_result(self):
        logger.debug("return_query_result")
        query_result_url = self.api_url + "async/query_result/" + self.query_id
        response = return_get_json(query_result_url, self.headers)
        logger.debug(f"response:\n{response}")
        return response


class LabUser:
    def __init__(self, username, groupname):
        user_entry = get_user_model().objects.get(username=username)
        lab_entry = Project.objects.get(groupname)

        self.user_id = user_entry.user_id
        self.project_id = o.project_id
    # def __init__(self, userdict):
        # self.count = userdict["count"]
        # self.groupname = userdict["groupname"]
        # self.size_sum = userdict["size_sum"]
        # self.size_sum_hum = userdict["size_sum_hum"]
        # self.username = userdict["username"]


class ColdFrontDB:

    def pull_sf(self, volume=None):
        labs_resources = self.generate_project_resource_dict()
        labs_resources = {k:[l.replace('holy-isilion', 'holy-isilon') for l in v] for k, v in labs_resources.items()}
        logger.debug(f"labs_resources:\n{labs_resources}")
        if volume != None:
            lr = {k:v for k, v in labs_resources.items() if volume in v}
            logger.debug(f"minimized labs_resources:\n{lr}")
        else:
            lr = labs_resources
        vol_set = {v[0] for v in lr.values()}
        # if volume:
        #     vol_set = {}
        logger.debug(f"vol_set: {vol_set}")
        serv_vols = generate_serv_vol_dict(vol_set)
        logger.debug(f"vol_set: {vol_set}")
        for s, v in serv_vols.items():
            server = StarFishServer(s)
            for vol, path in v.items():
                logger.debug(f"volume: {vol}")
                vol_labs_resources = {l:r for l, r in lr.items() if r[0] == vol}
                logger.debug(f"vol_labs_resources: {vol_labs_resources}")
                filepaths = collect_starfish_usage(server, vol, path, vol_labs_resources)
        return filepaths

    def push_cf(self, filepaths):
        for f in filepaths:
            content = read_json(f)
            statdicts = content['contents']
            for statdict in statdicts:
                try:
                    self.update_usage(statdict)
                    os.remove(f)
                except Exception as e:
                    logger.debug("EXCEPTION FOR ENTRY: {}".format(e),  exc_info=True)

    def generate_project_resource_dict(self):
        """
        Return dict with keys as project names and values as a list where [0] is the volume and [1] is the tier.
        """
        pr_entries = Allocation.objects.only("id", "project_id")
        # for a in pr_entries:
        #     print("a.get_resources_as_string", a.get_resources_as_string)
        pr_dict = {
            return_pname(o.project_id):o.get_resources_as_string for o in pr_entries}
        pr_dict = {p:r.split("/") for p, r in pr_dict.items()}
        logger.debug(f"project_resource_dict:\n{pr_dict}")
        return pr_dict

    def update_usage(self, userdict):
        # get ids needed to locate correct allocationuser entry
        # user = LabUser(userdict["username"], userdict["groupname"])
        user = get_user_model().objects.get(username=userdict["username"])
        project = Project.objects.get(title=userdict["groupname"])
        allocation = Allocation.objects.filter(project_id=project.id)
        a_id = [int(a.id) for a in allocation]
        logger.debug(f"EXCEPT a_id:{a_id}")
        try:
            allocationuser = AllocationUser.objects.get(
                allocation_id__in=a_id, user_id=user.id
            )
        except AllocationUser.DoesNotExist:
            filepath = './coldfront/plugins/sftocf/data/missing_allocationusers.csv'
            aid = "|".join([str(id) for id in a_id])
            datestr = datetime.today().strftime("%Y%m%d")
            pattern = f"{aid},{user.id},{user.username},{project.id},{project.title},{datestr}"
            write_update_file_line(filepath, pattern)
            raise AllocationUser.DoesNotExist
        allocationuser.usage_bytes = userdict["size_sum"]
        usage, unit = split_num_string(userdict["size_sum_hum"])
        allocationuser.usage = usage
        allocationuser.unit = unit
        # automatically updates "modified" field & adds old record to history
        allocationuser.save()
        logger.debug(f"successful entry: {userdict['groupname']}, {userdict['username']}")

def write_update_file_line(filepath, pattern):
    with open(filepath, 'r+') as f:
        if not any(pattern == line.rstrip('\r\n') for line in f):
            f.write(pattern + '\n')
            print("writing line...")
            f.write(newline)

def return_pname(pid):
    project = Project.objects.get(id=pid)
    return project.title

def split_num_string(x):
    n = re.search("\d*\.?\d+", x).group()
    s = x.replace(n, "")
    return n, s


def generate_volpath_strings(volpathdict):
    logger.debug("generate_volpath_strings")
    string_list = []
    for v, p in volpathdict.items():
        p = [f"{v}:{n}" for n in p if ".txt" not in n]
        string_list.extend(p)
    vpstring = "/".join(string_list)
    logger.debug(vpstring)
    return vpstring


def return_get_json(url, headers):
    response = requests.get(url, headers=headers)
    return response.json()

def save_as_json(file, contents):
    with open(file, "w") as fp:
        json.dump(contents, fp, sort_keys=True, indent=4)

def read_json(filepath):
    logger.debug("read_json for {}".format(filepath))
    with open(filepath, "r") as myfile:
        data = json.loads(myfile.read())
    return data

def confirm_dirpath_exists(dpath):
    isExist = os.path.exists(dpath)
    if not isExist:
      os.makedirs(path)
      logger.debug(f"created new directory {dpath}")


def collect_starfish_usage(server, volume, volumepath, projects):
    """

    Returns
    -------
    filepaths : list
        list of filepath names
    """
    filepaths = []
    datestr = datetime.today().strftime("%Y%m%d")
    logger.debug("server.name: {}".format(server.name))
    projects_reduced = {p:r for p,r in projects.items() if r[0] == volume}
    logger.debug(f"projects: {projects}\nprojects_reduced: {projects_reduced}")
    for p, r in projects_reduced.items():
        homepath = "./coldfront/plugins/sftocf/data/"
        filepath = f"{homepath}{p}_{server.name}_{datestr}.json"
        logger.debug(f"filepath 1: {filepath}")
        if Path(filepath).exists():
            filepaths.append(filepath)
        else:
            lab_volpath = volumepath# + "/{}".format(p)
            queryline = "type=f groupname={}".format(p)
            usage_query = server.create_query(
                queryline, "username, groupname", f"{volume}:{lab_volpath}", sec=2
            )
            data = usage_query.result
            logger.debug("usage_query.result:{}".format(data))
            if not data:
                logger.warning("No starfish result for lab {}".format(p))
            elif type(data) is dict and "error" in data:
                logger.warning("Error in starfish result for lab {}:\n{}".format(p, data))
            else:
                data = usage_query.result
                logger.debug(data)
                record = {
                    "server": server.name,
                    "volume": volume,
                    "path": lab_volpath,
                    "date": datestr,
                    "contents": data,
                }
                confirm_dirpath_exists(homepath)
                save_as_json(filepath, record)
                filepaths.append(filepath)
    return filepaths

# def collect_costperuser():
#     # get from billing record
#     author_id = ifx_user_id
#     account_id => account[lab_name]
#     product_usage_id links to product_usage table, containing
#
#
# id
# charge
# description
# year
# month
# created
# updated
# account_id
# product_usage_id
# current_state
# percent
# author_id
# updated_by_id
# rate

def clean_data_dir():
    """Remove json from data folder that's more than a week old
    """
    files = os.listdir("./coldfront/plugins/sftocf/data/")
    json_files = [f for f in files if ".json" in f]
    print(json_files)
    now = time.time()
    for f in json_files:
        fpath = f"./coldfront/plugins/sftocf/data/{f}"
        created = os.stat(fpath).st_ctime
        if created < now - 7 * 86400:
            os.remove(fpath)


def generate_serv_vol_dict(vol_set):
    search_svp = {}
    for s, v in svp.items():
        if any(vi in v.keys() for vi in vol_set):
            search_svp[s] = {}
            for vk, p in v.items():
                if vk in vol_set:
                    search_svp[s][vk] = p
    return search_svp