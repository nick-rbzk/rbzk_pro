
from django.urls import path
from .views import *


urlpatterns = [
    path("options/", trading_options, name="trading_options"),
]
