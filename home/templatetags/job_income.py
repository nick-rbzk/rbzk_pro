from django import template
import math
register = template.Library()

@register.filter
def job_income(job):
    total_seconds = (job.job_end - job.job_start).total_seconds()
    rate_per_second = 950 / 3600
    total = total_seconds * rate_per_second
    dollars = math.floor(total / 100)
    cents = math.floor(total % 100)

    return '{}.{}$'.format(dollars, cents)
