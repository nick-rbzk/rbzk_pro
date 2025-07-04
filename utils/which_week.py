from rbzk.settings import WEEK_TIME_START, WEEK_TIME_END
from datetime import datetime, timedelta
from django.utils import timezone

def which_week(job_end_datetime):
    if job_end_datetime is None or job_end_datetime == '':
        return None
    
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

    return timezone.make_aware(week_start_datetime),timezone.make_aware(week_end_datetime)