from django.contrib import admin
from .models import *
# Register your models here.

admin.site.register(WorkWeek)
admin.site.register(FormSubmission)

@admin.register(ParkJob)
class ParkJobAdmin(admin.ModelAdmin):
    list_display    = ("confirmation", "total", "job_start", "job_end")
    search_fields   = ("confirmation", "job_start", "job_end")

    def total(self, obj):
        return f"{obj.job_income()}"
    
    total.short_desctioption = "Total Income"
