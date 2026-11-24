import django.dispatch


allocation_autocreate = django.dispatch.Signal()
    #providing_args=["approval_form_data", "allocation_obj"]

allocation_autoupdate = django.dispatch.Signal()
    #providing_args=["allocation", "new_quota_value"]

allocation_activate = django.dispatch.Signal()
    #providing_args=["allocation_obj"]
allocation_disable = django.dispatch.Signal()
    #providing_args=["allocation_pk"]

allocation_activate_user = django.dispatch.Signal()
    #providing_args=["allocation_user_pk"]
allocation_remove_user = django.dispatch.Signal()
    #providing_args=["allocation_user_pk"]

allocation_change_approved = django.dispatch.Signal()
    #providing_args=["allocation_pk", "allocation_change_pk"]

allocation_user_attribute_edit = django.dispatch.Signal()
    #providing_args=["account", "user", "raw_share"]

allocation_user_remove_on_slurm = django.dispatch.Signal()
    #providing_args=["username", "account"]

allocation_raw_share_edit = django.dispatch.Signal()
    #providing_args=["account", "raw_share"]

allocation_user_add_on_slurm = django.dispatch.Signal()
    #providing_args=["username", "cluster", "account"]

allocation_set_zoneuserparam = django.dispatch.Signal()
    #providing_args=["zone_id", "param_name", "param_value"]

xdmod_account_usage = django.dispatch.Signal()
