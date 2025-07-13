from django.shortcuts import render

def cal_stats(request):
    return render(request, "cal_stats.html", {})