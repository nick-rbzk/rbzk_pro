from django.urls import path
from .views import *
urlpatterns = [
    # REST API endpoints
    path('api/websocket-status/', websocket_service_status, name='ws_status'),
    
    # SSE streaming endpoints
    path('api/stream/', subscribe_to_updates, name='price_stream_all'),
    path('', TradingDashboardView.as_view(), name='price_dashboard'),
    path('api/trading-pairs/', TradingPairsAPIView.as_view(), name='trading_pairs_api'),
    path('api/update-pairs/', UpdateTradingPairsAPIView.as_view(), name='update_pairs_api'),

]