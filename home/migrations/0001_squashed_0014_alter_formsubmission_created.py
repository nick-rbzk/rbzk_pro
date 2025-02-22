# Generated by Django 4.2.13 on 2025-01-23 01:25

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    replaces = [('home', '0001_initial'), ('home', '0002_parkjob_confirmation'), ('home', '0003_formsubmission'), ('home', '0004_formsubmission_created'), ('home', '0005_alter_formsubmission_created'), ('home', '0006_alter_formsubmission_created'), ('home', '0007_alter_formsubmission_created'), ('home', '0008_alter_formsubmission_created'), ('home', '0009_alter_formsubmission_created'), ('home', '0010_alter_formsubmission_created'), ('home', '0011_alter_formsubmission_created'), ('home', '0012_alter_formsubmission_created'), ('home', '0013_alter_formsubmission_created'), ('home', '0014_alter_formsubmission_created')]

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='WorkWeek',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('week_start', models.DateTimeField()),
                ('week_end', models.DateTimeField()),
                ('jobs_time', models.DurationField(null=True)),
            ],
            options={
                'ordering': ['week_end'],
            },
        ),
        migrations.CreateModel(
            name='ParkJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('job_start', models.DateTimeField()),
                ('job_end', models.DateTimeField()),
                ('notes', models.TextField()),
                ('workweek', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='home.workweek')),
                ('confirmation', models.CharField(max_length=1024, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='FormSubmission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(blank=True, max_length=2024, null=True)),
                ('email', models.CharField(blank=True, max_length=2024, null=True)),
                ('phone', models.CharField(blank=True, max_length=2024, null=True)),
                ('message', models.CharField(blank=True, max_length=2024, null=True)),
                ('navigators_match', models.BooleanField(default=False)),
                ('navigator_string_from_request', models.CharField(blank=True, max_length=2024, null=True)),
                ('navigator_string_from_js', models.CharField(blank=True, max_length=2024, null=True)),
                ('created', models.DateTimeField(default=django.utils.timezone.now)),
            ],
        ),
    ]
