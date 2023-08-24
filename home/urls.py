
from django.urls import path
from home.views import *
urlpatterns = [
    path("", home_page, name="home_page"),
]
