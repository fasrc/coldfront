from django.views.generic import ListView
from django.db.models.query import QuerySet
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator

def produce_filter_parameter(key, value):
    if isinstance(value, list):
        return ''.join([f'{key}={ele}&' for ele in value])
    if isinstance(value, QuerySet):
        return ''.join([f'{key}={ele.pk}&' for ele in value])
    if hasattr(value, 'pk'):
        return f'{key}={value.pk}&'
    return f'{key}={value}&'

# Create your views here.
class ColdfrontListView(LoginRequiredMixin, ListView):
    '''A ListView with definitions standard to complex ListView implementations in Coldfront
    '''

    def return_order(self):
        '''standardize the method for the 'order_by' value used in get_queryset'''
        order_by = self.request.GET.get('order_by', 'id')
        direction = self.request.GET.get('direction', '')
        if order_by != 'name':
            direction = '-' if direction == 'des' else ''
            order_by = direction + order_by
        return order_by

    def filter_parameters(self, SearchFormClass):
        search_form = SearchFormClass(self.request.GET)
        if search_form.is_valid():
            data = search_form.cleaned_data
            filter_parameters = ''
            for key, value in data.items():
                if value:
                    filter_parameters += produce_filter_parameter(key, value)
        else:
            filter_parameters = None
            search_form = SearchFormClass()
        order_by = self.request.GET.get('order_by')
        if order_by:
            direction = self.request.GET.get('direction')
            filter_parameters_with_order_by = filter_parameters + \
                f'order_by={order_by}&direction={direction}&'
        else:
            filter_parameters_with_order_by = filter_parameters

        return search_form, filter_parameters, filter_parameters_with_order_by


    def get_context_data(self, SearchFormClass=None, **kwargs):

        context = super().get_context_data(**kwargs)
        count = self.get_queryset().count()
        context['count'] = count

        search_form, filter_parameters, filter_parameters_with_order_by = self.filter_parameters(SearchFormClass)

        if filter_parameters:
            context['expand_accordion'] = 'show'

        item_list = context.get('item_list')
        paginator = Paginator(item_list, self.paginate_by)

        page = self.request.GET.get('page')

        try:
            item_list = paginator.page(page)
        except PageNotAnInteger:
            item_list = paginator.page(1)
        except EmptyPage:
            item_list = paginator.page(paginator.num_pages)

        context['search_form'] = search_form
        context['filter_parameters'] = filter_parameters
        context['filter_parameters_with_order_by'] = filter_parameters_with_order_by

        return context
