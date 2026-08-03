import os
from datetime import datetime
from django.contrib import admin
from django.contrib.admin import AdminSite
from django.urls import path, reverse
from django.shortcuts import render
from django.utils.html import format_html
from django.db.models import Count, Q, F
from django.contrib import messages

from django_celery_beat.models import PeriodicTask, IntervalSchedule,\
    CrontabSchedule, SolarSchedule, ClockedSchedule
from django_celery_beat.admin import PeriodicTaskAdmin, \
    TaskSelectWidget, CrontabScheduleAdmin

from home.models import ParkJob, WorkWeek
from utils.taxes import *

DOMAIN = os.environ.get("DOMAIN")

class CustomAdminSite(AdminSite):
    site_header = "RBZK"
    site_title = "Admin Site"
    index_title = "Admin Dashboard"
    # index_template = 'admin/custom_index.html'  # Optional custom index
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('dashboard/', self.admin_view(self.custom_dashboard), 
                 name='custom_dashboard'),
        ]
        return custom_urls + urls
    
    def get_app_list(self, request):
        """
        Override to add custom views to the admin index
        """
        app_list = super().get_app_list(request)
        # Add custom dashboard to the app list
        app_list.insert(0, {
            'name': 'Dashboard & Reports',
            'app_label': 'custom_dashboard',
            'app_url': reverse('AdminDashboardFlow:custom_dashboard'),
            'models': [
                {
                    'name': 'Dashboard',
                    'object_name': 'dashboard',
                    'admin_url': reverse('AdminDashboardFlow:custom_dashboard'),
                    'view_only': True,
                },
            ],
        })
        
        return app_list

    def tax_total(self, obj):
        income = float(obj.job_income()) 
        self_employ_owed = self_employ_tax(income)
        federal_owed = federal_income_tax(income)
        total = self_employ_owed + federal_owed
        return total
    
    def custom_dashboard(self, request):
        """Main custom dashboard"""
        jobs = ParkJob.objects.all() 
        
        # Get statistics
        stats = ParkJob.objects.aggregate(
            total_jobs=Count('id'),
            jobs_this_year=Count('id', filter=Q(
                job_start__gte=datetime(2026, 1, 1),
                job_start__lt=datetime(2027, 1, 1)
            )),
        )
        
        # Group by post_type
        # posts_by_type = Post.objects.values('post_type').annotate(
        #     count=Count('id')
        # ).order_by('-count')
        
        # Recent pending posts
        # recent_pending = Post.objects.filter(state=PostState.PENDING)[:5]
        jobs_this_year = ParkJob.objects.filter(Q(
                job_start__gte=datetime(2026, 1, 1),
                job_start__lt=datetime(2027, 1, 1))
            )
        income_total = 0
        tax_total = 0
        for j in jobs_this_year:
            income_total += float(j.job_income())
            tax_total += self.tax_total(j)
        income_after_tax = income_total  - tax_total
        income_after_tax =  '{0:.2f}$'.format(income_after_tax)
        income_total =  '{0:.2f}$'.format(income_total)
        tax_total =  '{0:.2f}$'.format(tax_total)

        context = dict(
            self.each_context(request),
            title="Dashboard Overview",
            jobs=jobs[:20],  # Show 10 most recent
            stats=stats,
            income_total=income_total,
            tax_total=tax_total,
            income_after_tax=income_after_tax,
            opts=ParkJob._meta,
        )

        # ("confirmation", "after_tax", "tax_total", "total", "jb_start", "jb_end")
        return render(request, 'admin/custom_dashboard.html', context)
    
    
admin_site = CustomAdminSite(name='AdminDashboardFlow')

admin_site.register(PeriodicTask, PeriodicTaskAdmin)
admin_site.register(IntervalSchedule)
admin_site.register(CrontabSchedule)
admin_site.register(SolarSchedule)
admin_site.register(ClockedSchedule)