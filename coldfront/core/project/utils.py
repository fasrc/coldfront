from datetime import date

from django.db.models import Q
from ifxbilling.models import BillingRecord

from coldfront.core.allocation.models import AllocationUser, AllocationUserStatusChoice
from coldfront.core.project.models import ProjectUser, ProjectUserStatusChoice
from coldfront.core.utils.common import import_from_settings
from coldfront.plugins.ifx.models import ProjectOrganization

EMAIL_SENDER = import_from_settings('EMAIL_SENDER')


def reactivate_storage_allocationusers(user):
    """Reactivate the user's AllocationUsers in active storage allocations of projects
    where they are an Active ProjectUser
    """
    AllocationUser.objects.filter(
        user=user,
        allocation__project__status__name__in=['Active', 'Renewal Requested'],
        allocation__status__name__in=['Active', 'Pending Deactivation'],
        allocation__project__projectuser__user=user,
        allocation__project__projectuser__status__name='Active',
        allocation__resources__resource_type__name='Storage'
    ).distinct().update(
        status=AllocationUserStatusChoice.objects.get(name='Active')
    )


def secondary_projectusers(user, project):
    """The user's Active ProjectUsers in active/new projects other than project"""
    return ProjectUser.objects.filter(
        user=user,
        status__name='Active',
        project__status__name__in=['Active', 'New'],
    ).exclude(project=project)


def deactivate_secondary_projectusers(user, project):
    """Deactivating a user's primary group disables their whole AD account but leaves their
    other AD group memberships alone, so their other projects' memberships become Deactivated,
    not Removed. Returns the titles of the projects changed.
    """
    projectusers = secondary_projectusers(user, project).select_related('project')
    titles = [pu.project.title for pu in projectusers]
    projectusers.update(status=ProjectUserStatusChoice.objects.get(name='Deactivated'))
    return titles


def generate_usage_history_graph(project):
    """Create a Project billing record graph.

    Returns
    -------
    data : dict
        contains
        columns : list
    """
    current_year = date.today().year
    previous_year = current_year - 1
    current_month = date.today().month

    # sort billing_records by year/month
    year_months = [(previous_year, month) for month in range(current_month, 13)] + [(current_year, month) for month in range(1, current_month+1)]
    allocations = project.allocation_set.all()
    columns = []
    projection = False
    for allocation in allocations:
        allocation_res = allocation.get_parent_resource.name
        allocation_billing_records = BillingRecord.objects.filter(
                (Q(year=current_year) | Q(year=previous_year, month__gte=current_month)),
                product_usage__product__product_name=allocation_res,
                account__organization=ProjectOrganization.objects.get(project=project).organization,
            )
        allocation_column = [allocation_res]
        projection = False
        for year_month in year_months:
            year = year_month[0]
            month = year_month[1]
            ym_records = allocation_billing_records.filter(year=year, month=month)
            if year == current_year and month == current_month and ym_records.count() == 0:
                projection = True
                ym_cost = allocation.cost
            elif ym_records.count() == 0:
                ym_cost = 0
            else:
                ym_cost = float(sum(r.decimal_charge for r in ym_records))

            allocation_column.append(ym_cost)
        columns.append(allocation_column)

    if not projection:
        columns.append(['month'] + [f'{ym[1]}/{ym[0]}' for ym in year_months])
    else:
        columns.append(['month'] +
                [f'{ym[1]}/{ym[0]}' for ym in year_months[:-1]] +
                [f'{current_month}/{current_year} (PROJECTED)'])

    data = {
        "x": "month",
        "columns": columns,
        "type": "bar",
        "order": "null",
        "groups": [[ allocation.get_parent_resource.name for allocation in allocations
                ]],
    }

    return data
