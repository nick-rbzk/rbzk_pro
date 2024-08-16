from django import template
import math
register = template.Library()

@register.filter
def income(td):
    total_seconds = int(td.total_seconds())
    rate_per_second = 1000 / 3600
    total = total_seconds * rate_per_second
    dollars = math.floor(total / 100)
    cents = math.floor(total % 100)

    return '{}.{}$'.format(dollars, cents)
