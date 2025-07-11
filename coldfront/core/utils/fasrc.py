"""A module for fasrc-specific utility functions.
"""
import os
import json
import logging
import operator
from functools import reduce
from datetime import datetime

import pandas as pd
from django.db.models import Q
from django.contrib.auth import get_user_model
from ifxbilling.models import Product

from coldfront.core.utils.common import import_from_settings
from coldfront.core.project.models import Project
from coldfront.core.resource.models import Resource

logger = logging.getLogger(__name__)

MISSING_DATA_DIR = './local_data/missing/'

username_ignore_list = import_from_settings('username_ignore_list', [])
groupname_ignore_list = import_from_settings('groupname_ignore_list', [])


def get_quarter_start_end():
    y = datetime.today().year
    quarter_starts = [f'{y}-01-01', f'{y}-04-01', f'{y}-07-01', f'{y}-10-01']
    quarter_ends = [f'{y}-03-31', f'{y}-06-30', f'{y}-09-30', f'{y}-12-31']
    quarter = (datetime.today().month-1)//3
    return (quarter_starts[quarter], quarter_ends[quarter])

def sort_by(list1, sorter, how='attr'):
    """split one list into two on basis of each item's ability to meet a condition
    Parameters
    ----------
    list1 : list
        list of objects to be sorted
    sorter : attribute or function
        attribute or function to be used to sort the list
    how : str
        type of sorter ('attr' or 'condition')
    """
    is_true, is_false = [], []
    for x in list1:
        if how == 'attr':
            (is_false, is_true)[getattr(x, sorter)].append(x)
        elif how == 'condition':
            (is_false, is_true)[sorter(x)].append(x)
        else:
            raise Exception('unclear sorting method')
    return is_true, is_false

def select_one_project_allocation(project_obj, resource_obj, dirpath):
    """
    Get one allocation for a given project/resource/path pairing; handle return of
    zero or multiple allocations.

    Parameters
    ----------
    project_obj
    resource_obj
    dirpath
    """
    allocation_query = project_obj.allocation_set.filter(
                    resources__id=resource_obj.id
    ).exclude(status__name='Merged')
    if allocation_query.count() < 1:
        return None
    else:
        allocations = [
            a for a in allocation_query
            if a.path and dirpath and (a.path in dirpath or dirpath in a.path)
        ]
        if len(allocations) == 1:
            return allocations[0]
        elif len(allocations) > 1:
            print(f'multiple allocations found for project/resource/path pairing: {allocations}, {allocations[0].path}')
            logger.exception('multiple allocations found for project/resource/path pairing: %s %s', allocations, allocations[0].path)
            raise Exception('multiple allocations found for project/resource/path pairing')

def return_unit_system(system):
    if system == 'binary':
        units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB']
        divisor = 1024.0
    elif system == 'decimal':
        units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB']
        divisor = 1000.0
    else:
        raise Exception('invalid system')
    return units, divisor

def determine_size_fmt(byte_num, system='binary'):
    """Return the correct human-readable byte measurement.
    """
    units, divisor = return_unit_system(system)
    for u in units:
        unit = u
        if abs(byte_num) < divisor:
            return (round(byte_num, 3), unit)
        byte_num /= divisor
    return (round(byte_num, 3), unit)

def convert_size_fmt(num, target_unit, source_unit='B', system='binary'):
    units, divisor = return_unit_system(system)
    diff = units.index(target_unit) - units.index(source_unit)
    if diff == 0:
        pass
    elif diff > 0:
        for i in range(diff):
            num/=divisor
    elif diff < 0:
        for i in range(abs(diff)):
            num*=divisor
    return round(num, 3)

def get_resource_rate(resource):
    """find Product with the name provided and return the associated rate"""
    try:
        resource_obj = Resource.objects.get(name=resource)
    except Resource.DoesNotExist:
        return None
    if resource_obj.resource_type.name == 'Storage Tier':
        return None
    prod_obj = Product.objects.get(product_name=resource)
    rate_obj = prod_obj.rate_set.get(is_active=True)
    if resource_obj.resource_type.name == "Cluster":
        return rate_obj.decimal_price
    # return charge per TB, adjusted to dollar value
    if rate_obj.units in ['TiB', 'TB']:
        return rate_obj.price/100
    price = convert_size_fmt(rate_obj.price, 'TiB', source_unit=rate_obj.units)
    return round(price/100, 2)

def id_present_missing_resources(resourceserver_list):
    """
    Collect all Resource entries with resources in param resourceserver_list;
    return tuple of all matching Resource entries and all servers with no Resource entries.
    """
    present_resources = Resource.objects.filter(reduce(operator.or_,
                    (Q(name__contains=x) for x in resourceserver_list)))
    res_names = [str(r.name).split('/')[0] for r in present_resources]
    missing_res = [res for res in resourceserver_list if res not in res_names]
    return (present_resources, missing_res)


def id_present_missing_projects(title_list):
    """
    Collect all Project entries with titles in param title_list; return tuple
    of all matching Project entries and all titles with no Project entries.
    """
    present_projects = Project.objects.filter(title__in=title_list)
    proj_titles = list(present_projects.values_list('title', flat=True))
    missing_project_titles = [
        {'title': title} for title in title_list
        if title not in proj_titles and title not in groupname_ignore_list
    ]
    return (present_projects, missing_project_titles)


def id_present_missing_projectusers(projectuser_tuple_list):
    """
    Collect all User entries with usernames in position [1] of projectuser_tuple_list
    tuples; return tuple consisting of all matching User entries and a list of
    dicts recording the project and user of missing entries.

    Parameters
    ----------
    projectuser_tuple_list : list of (project_title, username) tuples

    Returns
    -------
    present_users :
    missing_projectusers :
    """
    username_list = [tuple[1] for tuple in projectuser_tuple_list]
    present_users = get_user_model().objects.filter(username__in=username_list)
    present_usernames = list(present_users.values_list('username', flat=True))
    missing_projusers = [{'project': tuple[0], 'username':tuple[1]}
        for tuple in projectuser_tuple_list
        if tuple[1] not in present_usernames and tuple[1] not in username_ignore_list
    ]
    return (present_users, missing_projusers)


def id_present_missing_users(username_list):
    """
    Collect all User entries with usernames in param username_list; return tuple
    of all matching User entries and all usernames with no User entries.
    """
    present_users = get_user_model().objects.filter(username__in=username_list)
    present_usernames = list(present_users.values_list('username', flat=True))
    missing_usernames = [
        {'username': n} for n in username_list
        if n not in present_usernames and n not in username_ignore_list
    ]
    return (present_users, missing_usernames)


def log_missing(modelname, missing):
    """log missing entries for a given Coldfront model.
    Add or update entries in CSV, order CSV by descending date and save.

    Parameters
    ----------
    modelname : string
        lowercase name of the Coldfront model for "missing"
    missing : list of dicts
        identifying information to record for missing entries:
            for users, "username".
            for projects, "title".
            for allocations, "resource_name", "project_title", and "path".
    """
    update_csv(missing, MISSING_DATA_DIR, f'missing_{modelname}s.csv')

def slate_for_check(log_entries):
    """Add an issue encountered during runtime to a CSV for administrative review.

    Parameters
    ----------
    log_entries : list of dicts
        keys should be "error" (description of issue encountered),
        "program" (where encountered), "urls" (url(s) to related object detail
        pages), "detail" (exc_info, if necessary)
    """
    update_csv(log_entries, 'local_data/', 'program_error_checks.csv')

def update_csv(new_entries, dirpath, csv_name, date_update='date'):
    """Add or update entries in CSV, order CSV by descending date and save.

    Parameters
    ----------
    new_entries : list of dicts
        identifying information to record for missing entries:
        for users, "username".
        for projects, "title".
        for allocations, "resource_name", "project_title", and "path".
    dirpath : str
    csv_name : str
    date_update : str
    """
    if new_entries:
        locate_or_create_dirpath(dirpath)
        fpath = f'{dirpath}{csv_name}'
        try:
            df = pd.read_csv(fpath, parse_dates=[date_update])
        except FileNotFoundError:
            df = pd.DataFrame()
        except ValueError:
            df = pd.read_csv(fpath)
        new_records = pd.DataFrame(new_entries)
        col_checks = new_records.columns.values.tolist()
        new_records[date_update] = datetime.today()
        updated_df = (pd.concat([df, new_records])
                        .drop_duplicates(col_checks, keep='last')
                        .sort_values(date_update, ascending=False)
                        .reset_index(drop=True))
        updated_df.to_csv(fpath, index=False)


def locate_or_create_dirpath(dpath):
    if not os.path.exists(dpath):
        os.makedirs(dpath)


def read_json(filepath):
    with open(filepath, 'r') as json_file:
        data = json.loads(json_file.read())
    return data

def save_json(file, contents):
    with open(file, 'w') as fp:
        json.dump(contents, fp, sort_keys=True, indent=4)
