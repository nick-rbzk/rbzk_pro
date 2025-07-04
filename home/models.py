import pytz
from django.db import models
from datetime import datetime, timedelta
from django.dispatch import receiver
from django.db.models.signals import post_save, post_delete, pre_save
from django.utils import timezone
from utils.which_week import which_week


def get_local_date_time():
    utc = pytz.utc
    utc_dt = datetime.now(timezone.utc)
    eastern = pytz.timezone('America/New_York')
    loc_dt = utc_dt.astimezone(eastern)
    return loc_dt

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
        new_parent_week.parkjob_set.add(instance)
        all_jobs = new_parent_week.parkjob_set.all()
        total_duration = None
        for job in all_jobs:
            if total_duration is not None:
                total_duration = total_duration + (job.job_end - job.job_start).total_seconds()
            else:
                total_duration = (job.job_end - job.job_start).total_seconds()
        if total_duration is not None:
            new_parent_week.jobs_time = timedelta(seconds=total_duration)
        new_parent_week.save()
    current_parent_week.save()
    #kick off a background task to delete all empty workweeks
    empty_work_weeks = WorkWeek.objects.all().exclude(jobs_time__isnull=False)
    # print("Empty work weeks________________________________________")
    for e in empty_work_weeks:
        # print(e)
        # print(dir(e))
        e.delete()


@receiver(pre_save, sender=WorkWeek)
def week_update_hours(sender, instance, **kwargs):
    if instance.pk is not None:
        jobs_per_week = instance.parkjob_set.all()
        if len(jobs_per_week) > 0:
            total_duration = None
            for job in jobs_per_week:
                if total_duration is not None:
                    total_duration = total_duration + (job.job_end - job.job_start).total_seconds()
                else:
                    total_duration = (job.job_end - job.job_start).total_seconds()
            if total_duration is not None:
                instance.jobs_time = timedelta(seconds=total_duration)
        else:
            instance.jobs_time = None


@receiver(post_delete, sender=ParkJob)
def update_week_hours(sender, instance, **kwargs):
    work_week = instance.workweek
    jobs_per_week = work_week.parkjob_set.all()
    total_duration = None
    for job in jobs_per_week:
        if total_duration is not None:
            total_duration = total_duration + (job.job_end - job.job_start).total_seconds()
        else:
            total_duration = (job.job_end - job.job_start).total_seconds()
    if total_duration is not None:
        work_week.jobs_time = timedelta(seconds=total_duration)
    work_week.save()