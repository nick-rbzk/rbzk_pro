from django.contrib import admin
from rbzk.admin import admin_site
from .models import PriceBreakEmail

# Register your models here.

class PriceBreakEmailAdmin(admin.ModelAdmin):
    list_display = ('sent_on', 'product_id', 'created_at') 
    
admin_site.register(PriceBreakEmail, PriceBreakEmailAdmin)