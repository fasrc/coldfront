import logging
import django.dispatch

log = logging.getLogger(__name__)


project_create = django.dispatch.Signal()
    #providing_args=["project_title"]
project_post_create = django.dispatch.Signal()
    #providing_args=["project_obj"]

project_make_projectuser = django.dispatch.Signal()
    #providing_args=["user_name", "group_name"]

project_preremove_projectuser = django.dispatch.Signal()
    #providing_args=["user_name", "group_name"]

project_reactivate_projectuser = django.dispatch.Signal()

project_projectusers_status_change = django.dispatch.Signal()
    # providing_args=["projectusers", "new_status", "created"]
    # sent for bulk ProjectUser status changes that bypass post_save (queryset
    # .update() / bulk_create). projectusers must still hold their pre-change status.

project_filter_users_to_remove = django.dispatch.Signal()
    #providing_args=["project_user_list"]
    # return tuple of (no_removal, can_remove)

project_user_manager_ldap_groups_grant = django.dispatch.Signal()
    # providing_args=["user_name", "project_title"]

project_user_manager_ldap_groups_revoke = django.dispatch.Signal()
    # providing_args=["user_name", "project_title"]
