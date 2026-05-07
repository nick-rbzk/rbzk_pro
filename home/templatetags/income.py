import math
from django import template
register = template.Library()

@register.filter
def income(week):
    total_seconds = int(week.jobs_time.total_seconds())
    rate_per_second = week.hourly_rate / 3600
    total = total_seconds * rate_per_second
    dollars = math.floor(total / 100)
    cents = math.floor(total % 100)

    return '{}.{}$'.format(dollars, cents)
