'''
Admin for ifx
'''
import logging

from django.contrib import admin
from ifxuser.admin import UserAdmin
from coldfront.plugins.ifx.models import SuUser, ProjectOrganization


logger = logging.getLogger(__name__)

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
            actor = request.user.get_username() if request.user.is_authenticated else "anonymous"
            logger.info(
                "admin_su_login actor=%s target=%s target_pk=%s source=admin",
                actor,
                obj.get_username(),
                obj.pk,
            )
        return super().response_change(request, obj)


@admin.register(ProjectOrganization)
class ProjectOrganizationAdmin(admin.ModelAdmin):
    list_display = ('project', 'organization')
    search_fields = ('project__title', 'organization__name')
    autocomplete_fields = ('project', 'organization')
