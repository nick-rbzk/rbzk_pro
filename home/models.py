from django.db import models
from datetime import datetime
# Create your models here.


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