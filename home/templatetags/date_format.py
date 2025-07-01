from django import template
from django.utils import timezone
register = template.Library()

@register.filter
def date_format(date):
    # formated = date.strftime("%m/%d/%y %H:%M")
    # formated = f"{timezone.localtime(date):%m/%d/%Y %I:%M %p}"
    formated = f"{timezone.localtime(date):%m/%d/%y %H:%M}"
    return formated
