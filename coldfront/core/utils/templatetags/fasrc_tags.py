from django import template
from coldfront.core.utils.fasrc import get_resource_rate

register = template.Library()

@register.simple_tag(takes_context=True)
def cost_bytes(context, amount):
    a_price = get_resource_rate(context['allocation'].get_resources_as_string)
    amount_tb = int(amount) / 1099511627776
    if a_price:
        return "${:,.2f}".format(a_price * amount_tb)
    return None

@register.simple_tag(takes_context=True)
def cost_tb(context, amount):
    a_price = get_resource_rate(context['allocation'].get_resources_as_string)
    if a_price:
        return "${:,.2f}".format(a_price * amount)
    return None

@register.simple_tag(takes_context=True)
def cost_cpuhours(context, amount):
    a_price = get_resource_rate(context['allocation'].get_resources_as_string)
    if amount and a_price:
        return "${:,.2f}".format(float(a_price) * float(amount))
    return None

@register.inclusion_tag('resource_summary_table.html')
def resource_summary_table(resource):
    """
    """
    res_attr_table = {
        'Resource': resource,
        'Total space': resource.capacity,
    }
    allocated_tb = resource.allocated_tb
    if allocated_tb:
        allocated_pct = round(allocated_tb / resource.capacity * 100, 2)
        res_attr_table['Space Committed'] = f'{allocated_tb} ({allocated_pct}%)'
        remaining_space = resource.capacity * .85 - allocated_tb
        res_attr_table['Remaining Space (assuming 85% limit)'] = f'{remaining_space} TB'
    else:
        res_attr_table['Space Committed'] = 'Information not available; check the sheet.'
    if resource.free_capacity:
        res_attr_table['Space Occupied'] = f'{resource.used_percentage}%'

    return {'res_attr_table': res_attr_table}
