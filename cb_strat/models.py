from django.db import models

# Create your models here.

class ActiveTask(models.Model):
    task_id = models.CharField(max_length=256, blank=False, null=True)
    name = models.CharField(max_length=1024, blank=False, null=True)
    