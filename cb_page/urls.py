from django.urls import path
from .views import get_latest_price, get_all_prices, price_dashboard, \
      get_price_subscriber, subscribe_to_updates, websocket_service_status

urlpatterns = [
    path('', price_dashboard, name='price_dashboard'),
    # REST API endpoints
    path('api/price/<str:product_id>/', get_latest_price, name='get_price'),
    path('api/prices/', get_all_prices, name='get_all_prices'),
    path('api/websocket-status/', websocket_service_status, name='ws_status'),
    
    # SSE streaming endpoints
    path('api/stream/<str:product_id>/', subscribe_to_updates, name='price_stream'),
    path('api/stream/', subscribe_to_updates, name='price_stream_all'),
]