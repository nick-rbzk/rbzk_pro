from django import template
register = template.Library()

@register.filter
def date_format(date):
    formated = date.strftime("%m/%d/%y %H:%M")
    return formated
