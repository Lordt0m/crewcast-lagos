from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_forecastsnapshot_source_kind'),
    ]

    operations = [
        # The old seed command manufactured successful attempts. Preserve them
        # for audit, but do not count them as verified provider retrievals.
        migrations.AddField(
            model_name='syncattempt',
            name='source_kind',
            field=models.CharField(
                choices=[('worker', 'Background worker'), ('unknown', 'Legacy / unverified')],
                default='unknown',
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name='syncattempt',
            name='source_kind',
            field=models.CharField(
                choices=[('worker', 'Background worker'), ('unknown', 'Legacy / unverified')],
                default='worker',
                max_length=10,
            ),
        ),
    ]
