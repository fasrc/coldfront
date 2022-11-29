from collections import Counter

from django.conf import settings
from django.contrib.humanize.templatetags.humanize import intcomma
from django.db.models import Count, Q, Sum
from django.shortcuts import render
from django.views.decorators.cache import cache_page

from coldfront.core.allocation.models import Allocation, AllocationUser
from coldfront.core.portal.utils import (generate_allocations_chart_data,
                                         generate_publication_by_year_chart_data,
                                         generate_resources_chart_data,
                                         generate_volume_bar_graph)
from coldfront.core.project.models import Project
from coldfront.core.publication.models import Publication
from coldfront.core.resource.models import Resource
from coldfront.plugins.sftocf.utils import get_redash_vol_stats


def home(request):

    context = {}
    if request.user.is_authenticated:
        template_name = 'portal/authorized_home.html'
        project_list = Project.objects.filter(
            (Q(pi=request.user) & Q(status__name__in=['New', 'Active', ])) |
            (Q(status__name__in=['New', 'Active', ]) &
             Q(projectuser__user=request.user) &
             Q(projectuser__status__name__in=['Active', ]))
        ).distinct().order_by('-created')[:5]

        allocation_list = Allocation.objects.filter(
            Q(status__name__in=['Active', 'New', 'Renewal Requested', ]) &
            Q(project__status__name__in=['Active', 'New']) &
            Q(project__projectuser__user=request.user) &
            Q(project__projectuser__status__name__in=['Active', ]) &
                (Q(project__projectuser__role_id=1) |
                Q(allocationuser__user=request.user) &
                Q(allocationuser__status__name='Active'))
        ).distinct().order_by('-created')[:5]
        context['project_list'] = project_list
        context['allocation_list'] = allocation_list
        try:
            context['ondemand_url'] = settings.ONDEMAND_URL
        except AttributeError:
            pass
    else:
        template_name = 'portal/nonauthorized_home.html'

    context['EXTRA_APPS'] = settings.INSTALLED_APPS

    if 'coldfront.plugins.system_monitor' in settings.INSTALLED_APPS:
        from coldfront.plugins.system_monitor.utils import get_system_monitor_context
        context.update(get_system_monitor_context())

    return render(request, template_name, context)


def center_summary(request):
    context = {}

    # Publications Card
    publications = Publication.objects.filter(year__gte=1999).values('unique_id', 'year')
    publications_by_year = list(publications.distinct().values('year').annotate(
                                    num_pub=Count('year')).order_by('-year'))

    publications_by_year = [(ele['year'], ele['num_pub'])
                            for ele in publications_by_year]

    publication_by_year_bar_chart_data = generate_publication_by_year_chart_data(
        publications_by_year)
    context['publication_by_year_bar_chart_data'] = publication_by_year_bar_chart_data
    context['total_publications_count'] = publications.distinct().count()


    # Storage Card
    volumes = get_redash_vol_stats()
    volumes = [
        {
            "name": vol['volume_name'],
            "quota_TB": vol['capacity_TB'],
            'free_TB': vol['free_TB'],
            'used_TB': vol['used_physical_TB'],
            'regular_files': vol['regular_files'],
        }
        for vol in volumes
    ]
    # collect user and lab counts, allocation sizes for each volume

    for volume in volumes:
        resource = Resource.objects.get(name__contains=volume['name'])

        resource_allocation = Allocation.objects.filter(status__name="Active", resources=resource)

        allocation_sizes = [float(allocation.size) for allocation in resource_allocation]
        # volume['avgsize'] = allocation_sizes
        volume['avgsize'] = round(sum(allocation_sizes)/len(allocation_sizes), 2)

        project_ids = set(resource_allocation.values_list("project"))
        volume['lab_count'] = len(project_ids)
        user_ids = {user.pk for allocation in resource_allocation for user in allocation.allocation_users}
        volume['user_count'] = len(user_ids)

    context['volumes'] = volumes



    # # Tier Stats
    #
    # resource_names = Resource.objects.values("name")
    # new = []
    # for n in [vol['name'] for vol in volumes]:
    #     match = next(r.split("/")[1] for r in resource_names if n in r)
    #     new.append(match)
    # # storage_stats['names'] = new




    # Combined Resource Stats

    names = [vol['name'] for vol in volumes]
    free_tb = [vol['free_TB'] for vol in volumes]
    usage_tb = [vol['used_TB'] for vol in volumes]

    names.insert(0, "names")
    usage_tb.insert(0, "usage (TB)")
    free_tb.insert(0, "quota (TB)")

    storage_data_columns = [ usage_tb, free_tb,names, ]

    context['storage_data_columns'] = storage_data_columns

    resource_chart_data = {
        "x": "Resource Type",
        "columns": [
            ['Resource Type', 'Storage'],
            ['Used', round(sum(usage_tb[1:]), 2)],
            ['Capacity', round(sum(free_tb[1:]), 2)],
        ],
        "type": "bar",
        "order":"null",
        "groups": [['Used', 'Capacity',]],
        "colors": {
            "Capacity": '#000'
        }
    }
    context['resource_chart_data'] = resource_chart_data


    return render(request, 'portal/center_summary.html', context)


def help_page(request):
    context = {}
    return render(request, 'portal/help_page.html', context)



@cache_page(60 * 15)
def allocation_by_fos(request):

    allocations_by_fos = Counter(list(Allocation.objects.filter(
        status__name='Active').values_list('project__field_of_science__description', flat=True)))

    user_allocations = AllocationUser.objects.filter(
        status__name='Active', allocation__status__name='Active')

    active_users_by_fos = Counter(list(user_allocations.values_list(
        'allocation__project__field_of_science__description', flat=True)))
    total_allocations_users = user_allocations.values(
        'user').distinct().count()

    active_pi_count = Project.objects.filter(status__name__in=['Active', 'New']).values_list(
        'pi__username', flat=True).distinct().count()
    context = {}
    context['allocations_by_fos'] = dict(allocations_by_fos)
    context['active_users_by_fos'] = dict(active_users_by_fos)
    context['total_allocations_users'] = total_allocations_users
    context['active_pi_count'] = active_pi_count
    return render(request, 'portal/allocation_by_fos.html', context)


@cache_page(60 * 15)
def allocation_summary(request):

    allocation_resources = [
        allocation.get_parent_resource.parent_resource if allocation.get_parent_resource.parent_resource else allocation.get_parent_resource for allocation in Allocation.objects.filter(status__name='Active')]

    allocations_count_by_resource = dict(Counter(allocation_resources))

    allocation_count_by_resource_type = dict(
        Counter([ele.resource_type.name for ele in allocation_resources]))

    allocations_chart_data = generate_allocations_chart_data()
    resources_chart_data = generate_resources_chart_data(
        allocation_count_by_resource_type)

    context = {}
    context['allocations_chart_data'] = allocations_chart_data
    context['allocations_count_by_resource'] = allocations_count_by_resource
    context['resources_chart_data'] = resources_chart_data

    return render(request, 'portal/allocation_summary.html', context)
