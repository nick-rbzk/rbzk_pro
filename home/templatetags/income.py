from django import template
register = template.Library()
SECONDS_PER_HOUR = 3600
@register.filter
def income(week):
    total_seconds = int(week.jobs_time.total_seconds())
    rate_per_second = week.hourly_rate / SECONDS_PER_HOUR
    total = total_seconds * rate_per_second
    dollars = '{0:.0f}'.format(total / 100)
    cents = '{0:.0f}'.format(total % 100)

    return '{}.{}$'.format(dollars, cents)
