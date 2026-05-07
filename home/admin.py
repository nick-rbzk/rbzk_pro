from django.contrib import admin
from django.utils import timezone
from .models import *
# Register your models here.

admin.site.register(FormSubmission)

@admin.register(ParkJob)
class ParkJobAdmin(admin.ModelAdmin):
    list_display    = ("confirmation", "total", "jb_start", "jb_end")
    list_filter     = ("job_start", "job_end")
    search_fields   = ("confirmation", "job_start", "job_end")

    def jb_start(self, obj):
        return f"{timezone.localtime(obj.job_start):%m/%d/%Y %I:%M %p}"
    
    jb_start.admin_order_field = 'timefield'
    jb_start.short_description = 'Job Start'  
    
    def jb_end(self, obj):
        return f"{timezone.localtime(obj.job_end):%m/%d/%Y %I:%M %p}"
    
    jb_end.admin_order_field = 'timefield'
    jb_end.short_description = 'Job End'
 
    def total(self, obj):
        return f"{obj.job_income()}"
    
    total.short_desctioption = "Total Income"


@admin.register(WorkWeek)
class WorkWeekAdmin(admin.ModelAdmin):
    list_display    = ("week_start", "week_end", "jobs_time", "week_total", "hourly_rate")
    list_filter     = ("week_start", "week_end")
    search_fields   = ("jobs_time",)

    def week_total(self, obj):
        total_seconds = int(obj.jobs_time.total_seconds())
        rate_per_second = obj.hourly_rate / 3600
        total = total_seconds * rate_per_second
        dollars = '{0:.0f}'.format(total / 100)
        cents = '{0:.0f}'.format(total % 100)
        return '{}.{}$'.format(dollars, cents)
    
    # week_total.admin_order_field = 'timefield'
    week_total.short_description = 'Week\'s Total'  
    