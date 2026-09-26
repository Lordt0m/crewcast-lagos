from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_budgetwindow_source_kind'),
    ]

    operations = [
        migrations.CreateModel(
            name='ScheduledForecastRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('started_at', models.DateTimeField()),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(choices=[('running', 'Running'), ('completed', 'Completed'), ('failed', 'Failed')], default='running', max_length=12)),
                ('attempt_count', models.PositiveIntegerField(default=0)),
                ('error_type', models.CharField(blank=True, max_length=100)),
            ],
            options={'ordering': ['-started_at', '-pk']},
        ),
    ]
