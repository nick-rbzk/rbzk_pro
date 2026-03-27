from django.contrib import admin
from .models import WebSocketTask, TradingPair, DayPriceLog

# Register your models here.
admin.site.register(TradingPair)
admin.site.register(WebSocketTask)
admin.site.register(DayPriceLog)