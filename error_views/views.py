from django.shortcuts import render
from django.http import HttpResponse
from django.template.loader import render_to_string
# Create your views here.


def bad_request(request, exception=None):
    rendered = render_to_string('400.html')
    return HttpResponse(rendered, status=400)

def not_found(request, exception=None):
    rendered = render_to_string('404.html')
    return HttpResponse(rendered, status=404)

def server_error(request, exception=None):
    rendered = render_to_string('500.html')
    return HttpResponse(rendered, status=500)

def permission_denied(request, exception=None):
    rendered = render_to_string('403.html')
    return HttpResponse(rendered, status=403)
