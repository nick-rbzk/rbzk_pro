
from django.urls import path
from .views import *


urlpatterns = [
    path("options/", trading_options, name="trading_options"),
    path("stop-watch/<uuid:task_id>", stop_price_watcher, name="stop_watch"),
    path("stop-watch/", stop_price_watcher, name="stop_watch"),
    path("get-latest/", get_latest_price, name="get_latest"),
]
