
from django.urls import path
from home.views import *
urlpatterns = [
    path("", home_page, name="home_page"),
    path("jobs/", jobs_page, name="jobs_page"),
    path("contact-api/", contact_api, name="contact_api"),
]
