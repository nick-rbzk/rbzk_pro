import base64
import json
from datetime import datetime

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.gzip import gzip_page
from django.views.decorators.cache import never_cache
from utils.which_week import which_week

from .models import *
from .forms import *


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


@gzip_page
def home_page(request):
    return render(request, "home.html")


def contact_api(request):
    navigator_from_request = request.META['HTTP_USER_AGENT']
    decoded = request.body.decode('ascii')
    body = json.loads(decoded)
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

@never_cache
def jobs_page(request):
    context = {}
    context['form'] = JobForm()
    context["weeks"] = WorkWeek.objects.all().exclude(jobs_time__isnull=True)
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
        job_start_datetime = timezone.make_aware(datetime.strptime(job_start, '%m/%d/%Y %H:%M'))
        job_end_datetime = timezone.make_aware(datetime.strptime(job_end, '%m/%d/%Y %H:%M'))

        week_start_datetime, week_end_datetime = which_week(job_end_datetime)
        if isinstance(week_start_datetime, datetime) and isinstance(week_end_datetime, datetime):
            week, created = WorkWeek.objects.get_or_create(
                week_start=week_start_datetime, 
                week_end=week_end_datetime
            )
            if not created:
                week.save()
            # add a job to that week
            job, created = ParkJob.objects.get_or_create(
                job_start=job_start_datetime,
                job_end=job_end_datetime,
                confirmation=confirmation,
                notes=notes,
                workweek=week,
            )
            if not created:
                job.save()
        context["weeks"] = WorkWeek.objects.all()
        context["form"] = JobForm()
        return render(request, "jobs.html", context)
    else:
        return render(request, "jobs.html", context)