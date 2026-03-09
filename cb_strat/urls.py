
from django.urls import path
from .views import *


urlpatterns = [
    path("start-watch/", start_price_watcher, name="start_watch"),
    path("stop-watch/", stop_price_watcher, name="stop_watch"),
    path("get-latest/", get_latest_price, name="get_latest"),
]
