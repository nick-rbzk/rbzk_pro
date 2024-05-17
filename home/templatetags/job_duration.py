from django import template
import math
register = template.Library()

@register.filter
def job_duration(job):
    total_seconds = int((job.job_end - job.job_start).total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60

    return '{}H {}M'.format(hours, minutes)
