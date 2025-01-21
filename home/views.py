import base64
import json

from django.shortcuts import render
from datetime import datetime, timedelta
from django.http import JsonResponse
from .models import *
from .forms import *


WEEK_TIME_START = "00:00"
WEEK_TIME_END = "23:59"

def escape(htmlstring):
    escapes = {'\"': '&quot;',
               '\'': '&#39;',
               '<': '&lt;',
               '>': '&gt;'}
    # This is done first to prevent escaping other escapes.
    htmlstring = htmlstring.replace('&', '&amp;')
    for seq, esc in escapes.items():
        htmlstring = htmlstring.replace(seq, esc)
    return htmlstring

def home_page(request):
    import datetime
    import pytz

    utc = pytz.utc
    utc_dt = datetime.datetime.now(datetime.timezone.utc)
    eastern = pytz.timezone('US/Eastern')
    loc_dt = utc_dt.astimezone(eastern)
    fmt = '%Y-%m-%d %H:%M:%S %Z%z'
    print(loc_dt.strftime(fmt))

    print(datetime.datetime.now(datetime.timezone.utc))
    # 2019-09-05 08:10:29.910137+00:00

    return render(request, "home.html")

def contact_api(request):
    navigator_from_request = request.META['HTTP_USER_AGENT']
    decoded = request.body.decode('ascii')
    body = json.loads(decoded)
    print(body)
    if "token" in body:
        b_navigator_js = base64.b64decode(body["token"])
        navigator_from_js = escape(b_navigator_js.decode('ascii'))
    if "name" in body["submissionObject"]:
        name = escape(body["submissionObject"]["name"])
    if "email" in body["submissionObject"]:
        email = escape(body["submissionObject"]["email"])
    if "phone" in body["submissionObject"]:
        phone = escape(body["submissionObject"]["phone"])
    if "message" in body["submissionObject"]:
        message = escape(body["submissionObject"]["message"])
    if navigator_from_request == navigator_from_js:
        navigators_match = True


    try:
        FormSubmission.objects.create(
            name=name,
            email=email,
            message=message,
            phone=phone,
            navigators_match=navigators_match,
            navigator_string_from_js=navigator_from_js,
            navigator_string_from_request=navigator_from_request,
        )
    except Exception as e:
        print(e)
    return JsonResponse({"response": 200})

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
        confirmation = data.get("confirmation")
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
            confirmation=confirmation,
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