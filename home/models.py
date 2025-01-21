import pytz
from django.db import models
from datetime import datetime, timezone

utc = pytz.utc
utc_dt = datetime.now(timezone.utc)
eastern = pytz.timezone('US/Eastern')
loc_dt = utc_dt.astimezone(eastern)


class WorkWeek(models.Model):
    week_start  = models.DateTimeField()
    week_end    = models.DateTimeField()
    jobs_time   = models.DurationField(null=True)
    
    def __str__(self):
        return f"Week Start: {datetime.strftime(self.week_start, '%m/%d/%Y %H:%M')} \
            Week End: {datetime.strftime(self.week_end, '%m/%d/%Y %H:%M')}"
    
    class Meta:
        ordering = ["week_end"]



class ParkJob(models.Model):
    job_start       = models.DateTimeField()
    job_end         = models.DateTimeField()
    confirmation    = models.CharField(max_length=1024, blank=False, null=True)
    notes           = models.TextField()
    workweek        = models.ForeignKey(WorkWeek, on_delete=models.CASCADE)

    def __str__(self):
        return f"Job Start: {datetime.strftime(self.job_start, '%m/%d/%Y %H:%M')} \
            Job End: {datetime.strftime(self.job_end, '%m/%d/%Y %H:%M')}"


class FormSubmission(models.Model):
    name = models.CharField(max_length=2024, blank=True, null=True)
    email = models.CharField(max_length=2024, blank=True, null=True)
    phone = models.CharField(max_length=2024, blank=True, null=True)
    message = models.CharField(max_length=2024, blank=True, null=True)
    navigators_match = models.BooleanField(default=False)
    navigator_string_from_request = models.CharField(max_length=2024, blank=True, null=True)
    navigator_string_from_js = models.CharField(max_length=2024, blank=True, null=True)
    created = models.DateTimeField(default=loc_dt)

    def __str__(self):
        return f"Submitted by {self.name} on {self.created:%m/%d/%Y - %H:%M}"