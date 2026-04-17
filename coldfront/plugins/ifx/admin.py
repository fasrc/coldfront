'''
Admin for ifx
'''
from django.contrib import admin
from ifxuser.admin import UserAdmin
from coldfront.core.utils.common import log_su_impersonation
from coldfront.plugins.ifx.models import SuUser, ProjectOrganization


@admin.register(SuUser)
class SuUserAdmin(UserAdmin):
    '''
    Mainly for su-ing
    '''
    change_form_template = "admin/auth/user/change_form.html"
    change_list_template = "admin/auth/user/change_list.html"

    def response_change(self, request, obj):
        # django-su submits `_su` from the custom admin user change form.
        if "_su" in request.POST:
            log_su_impersonation(request.user, obj, source='admin')
        return super().response_change(request, obj)


@admin.register(ProjectOrganization)
class ProjectOrganizationAdmin(admin.ModelAdmin):
    list_display = ('project', 'organization')
    search_fields = ('project__title', 'organization__name')
    autocomplete_fields = ('project', 'organization')
