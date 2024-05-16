from django.shortcuts import render
from datetime import datetime, timedelta

from .models import *
from .forms import *


WEEK_TIME_START = "00:00"
WEEK_TIME_END = "23:59"

def home_page(request):
    return render(request, "home.html")


def jobs_page(request):
    context = {} 
    context['form'] = JobForm()
    context["weeks"] = WorkWeek.objects.all().reverse()
    context["is_logged_in"] = request.user.is_authenticated
    if request.method == "POST":
        data = request.POST
        job_start_date = data.get("job_start_date")
        job_start_time= data.get("job_start_time")
        job_end_date= data.get("job_end_date")
        job_end_time = data.get("job_end_time")
        notes = data.get("notes")
        
        job_start = job_start_date.strip() + " " + job_start_time.strip()
        job_end = job_end_date.strip() + " " + job_end_time.strip()
        job_start_datetime = datetime.strptime(job_start, '%m/%d/%Y %H:%M')
        job_end_datetime = datetime.strptime(job_end, '%m/%d/%Y %H:%M')

        if job_end_datetime.weekday() == 0:
            #print("JOB END is: Monday")
            week_start_datetime = job_end_datetime - timedelta(days=2)
            week_start = week_start_datetime.strftime("%m/%d/%Y") +" "+ WEEK_TIME_START
            week_start_datetime = datetime.strptime(week_start, '%m/%d/%Y %H:%M') 
            week_end_datetime = job_end_datetime + timedelta(days=4)
            week_end = week_end_datetime.strftime("%m/%d/%Y") + " " + WEEK_TIME_END
            week_end_datetime = datetime.strptime(week_end, '%m/%d/%Y %H:%M')
        elif job_end_datetime.weekday() == 1:
            #print("JOB END is: Tuesday")
            week_start_datetime = job_end_datetime - timedelta(days=3)
            week_start = week_start_datetime.strftime("%m/%d/%Y") +" "+ WEEK_TIME_START
            week_start_datetime = datetime.strptime(week_start, '%m/%d/%Y %H:%M') 
            week_end_datetime = job_end_datetime + timedelta(days=3)
            week_end = week_end_datetime.strftime("%m/%d/%Y") + " " + WEEK_TIME_END
            week_end_datetime = datetime.strptime(week_end, '%m/%d/%Y %H:%M')
        elif job_end_datetime.weekday() == 2:
            #print("JOB END is: Wednesday")
            week_start_datetime = job_end_datetime - timedelta(days=4)
            week_start = week_start_datetime.strftime("%m/%d/%Y") +" "+ WEEK_TIME_START
            week_start_datetime = datetime.strptime(week_start, '%m/%d/%Y %H:%M') 
            week_end_datetime = job_end_datetime + timedelta(days=2)
            week_end = week_end_datetime.strftime("%m/%d/%Y") + " " + WEEK_TIME_END
            week_end_datetime = datetime.strptime(week_end, '%m/%d/%Y %H:%M')
        elif job_end_datetime.weekday() == 3:
            #print("JOB END is: Thursday")
            week_start_datetime = job_end_datetime - timedelta(days=5)
            week_start = week_start_datetime.strftime("%m/%d/%Y") +" "+ WEEK_TIME_START
            week_start_datetime = datetime.strptime(week_start, '%m/%d/%Y %H:%M') 
            week_end_datetime = job_end_datetime + timedelta(days=1)
            week_end = week_end_datetime.strftime("%m/%d/%Y") + " " + WEEK_TIME_END
            week_end_datetime = datetime.strptime(week_end, '%m/%d/%Y %H:%M')
        elif job_end_datetime.weekday() == 4:
            #print("JOB END is: Friday")
            week_start_datetime = job_end_datetime - timedelta(days=6)
            week_start = week_start_datetime.strftime("%m/%d/%Y") +" "+ WEEK_TIME_START
            week_start_datetime = datetime.strptime(week_start, '%m/%d/%Y %H:%M') 
            week_end_datetime = job_end_datetime
            week_end = week_end_datetime.strftime("%m/%d/%Y") + " " + WEEK_TIME_END
            week_end_datetime = datetime.strptime(week_end, '%m/%d/%Y %H:%M')
        elif job_end_datetime.weekday() == 5:
            #print("JOB END is: Saturday")
            week_start_datetime = job_end_datetime
            week_start = week_start_datetime.strftime("%m/%d/%Y") +" "+ WEEK_TIME_START
            week_start_datetime = datetime.strptime(week_start, '%m/%d/%Y %H:%M')

            week_end_datetime = job_end_datetime + timedelta(days=6)
            week_end = week_end_datetime.strftime("%m/%d/%Y") + " " + WEEK_TIME_END
            week_end_datetime = datetime.strptime(week_end, '%m/%d/%Y %H:%M')
        else:
            #print("JOB END is: Sunday")
            week_start_datetime = job_end_datetime - timedelta(days=1)
            week_start = week_start_datetime.strftime("%m/%d/%Y") +" "+ WEEK_TIME_START
            week_start_datetime = datetime.strptime(week_start, '%m/%d/%Y %H:%M')

            week_end_datetime = job_end_datetime + timedelta(days=5)
            week_end = week_end_datetime.strftime("%m/%d/%Y") + " " + WEEK_TIME_END
            week_end_datetime = datetime.strptime(week_end, '%m/%d/%Y %H:%M') 

        # go to db retreive a week according to week_start and week_end
        week, created = WorkWeek.objects.get_or_create(
            week_start=week_start_datetime, 
            week_end=week_end_datetime
        )

        # add a job to that week
        job, created = ParkJob.objects.get_or_create(
            job_start=job_start_datetime,
            job_end=job_end_datetime,
            notes=notes,
            workweek=week,
        )
        jobs_per_week = week.parkjob_set.all()
        total_duration = None
        for job in jobs_per_week:
            if total_duration is not None:
                total_duration = total_duration + (job.job_end - job.job_start).total_seconds()
            else:
                total_duration = (job.job_end - job.job_start).total_seconds()
        week.jobs_time = timedelta(seconds=total_duration)
        week.save()
        context["weeks"] = WorkWeek.objects.all().reverse()
        context["form"] = JobForm()
        return render(request, "jobs.html", context)
        # get all the weeks, sort by the latest one.
        # display weeks and jobs in the template
        # display total week time in the template


    return render(request, "jobs.html", context)