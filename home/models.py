import pytz
from django.db import models
from datetime import datetime
from django.dispatch import receiver
from django.db.models.signals import post_save, post_delete
from django.utils import timezone
from utils.which_week import which_week
from utils.update_week_hours import update_workweek_hours



class WorkWeek(models.Model):
    week_start  = models.DateTimeField()
    week_end    = models.DateTimeField()
    jobs_time   = models.DurationField(null=True)
    
    def __str__(self):
        return f"START: {timezone.localtime(self.week_start):'%m/%d/%Y %H:%M'}  \
            |||  END: {timezone.localtime(self.week_end):'%m/%d/%Y %H:%M'}"
    
    class Meta:
        ordering = ["-week_end"]


class ParkJob(models.Model):
    job_start       = models.DateTimeField()
    job_end         = models.DateTimeField()
    confirmation    = models.CharField(max_length=1024, blank=False, null=True)
    notes           = models.TextField(blank=True, null=True)
    workweek        = models.ForeignKey(WorkWeek, on_delete=models.CASCADE)

    def __str__(self):
        return f"START - {timezone.localtime(self.job_start):%m/%d/%Y %I:%M %p}  \
            |||  END - {timezone.localtime(self.job_end):%m/%d/%Y %I:%M %p}"
    
    class Meta:
        ordering = ["-job_end"]


class FormSubmission(models.Model):
    name = models.CharField(max_length=2024, blank=True, null=True)
    email = models.CharField(max_length=2024, blank=True, null=True)
    phone = models.CharField(max_length=2024, blank=True, null=True)
    message = models.CharField(max_length=2024, blank=True, null=True)
    navigators_match = models.BooleanField(default=False)
    navigator_string_from_request = models.CharField(max_length=2024, blank=True, null=True)
    navigator_string_from_js = models.CharField(max_length=2024, blank=True, null=True)
    created = models.DateTimeField(auto_now_add=False, auto_now=False, default=timezone.now)

    def __str__(self):
        return f"Submitted by {self.name} on {timezone.localtime(self.created):%m/%d/%Y %I:%M %p}"


@receiver(post_save, sender=ParkJob)
def update_week_hours(sender, instance, **kwargs):
    current_parent_week = instance.workweek
    job_end_time = instance.job_end
    week_start, week_end = which_week(job_end_time)
    if isinstance(week_start, datetime) and isinstance(week_end, datetime):
        new_parent_week, created = WorkWeek.objects.get_or_create(
            week_start=week_start, 
            week_end=week_end
        )
        if created:
            new_parent_week.parkjob_set.add(instance)
            update_workweek_hours(new_parent_week)
            update_workweek_hours(current_parent_week)
        else:
            update_workweek_hours(new_parent_week)
    #kick off a background task to delete all empty workweeks
    empty_work_weeks = WorkWeek.objects.all().exclude(jobs_time__isnull=False)
    for e in empty_work_weeks:
        e.delete()


@receiver(post_delete, sender=ParkJob)
def update_week_hours_after_job_delete(sender, instance, **kwargs):
    work_week = instance.workweek
    update_workweek_hours(work_week)