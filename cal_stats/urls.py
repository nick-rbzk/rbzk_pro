
from django.urls import path
from .views import *
urlpatterns = [
    path("calendar/", cal_stats, name="cal_stats"),
]
