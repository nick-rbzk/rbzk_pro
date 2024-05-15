from django.shortcuts import render
from .forms import *
# Create your views here.

def home_page(request):
    return render(request, "home.html")

def jobs_page(request):
    context = {} 
    context['form'] = JobForm()
    if request.method == "POST":
        data = request.POST
        job_start_date = data.get("job_start_date")
        job_end_date = data.get("job_end_date")
        print(job_start_date)
        print(job_end_date)
    return render(request, "jobs.html", context)