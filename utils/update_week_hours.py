from datetime import timedelta

def update_workweek_hours(work_week):
    from home.models import WorkWeek
    if work_week.pk is not None and isinstance(work_week, WorkWeek):
        jobs_per_week = work_week.parkjob_set.all()
        if len(jobs_per_week) > 0:
            total_duration = None
            for job in jobs_per_week:
                if total_duration is not None:
                    total_duration = total_duration + (job.job_end - job.job_start).total_seconds()
                else:
                    total_duration = (job.job_end - job.job_start).total_seconds()
            if total_duration is not None:
                work_week.jobs_time = timedelta(seconds=total_duration)
        else:
            work_week.jobs_time = None
        work_week.save()

