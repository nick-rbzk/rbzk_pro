from django.shortcuts import render

# Create your views here.

def cal_stats(request):
    return render(request, "cal_stats.html", {})