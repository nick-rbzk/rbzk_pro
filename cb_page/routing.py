from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/prices/$', consumers.PriceConsumer.as_asgi()),
    re_path(r'ws/prices/(?P<product_id>\w+-\w+)/$', consumers.PriceConsumer.as_asgi()),
]