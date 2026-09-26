from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_providercircuitstate'),
    ]

    operations = [
        # Existing snapshots may have been created by the old demo seed command.
        # Conservatively withhold live attribution until a new provider sync.
        migrations.AddField(
            model_name='forecastsnapshot',
            name='source_kind',
            field=models.CharField(
                choices=[('provider', 'Provider retrieval'), ('unknown', 'Legacy / unverified')],
                default='unknown',
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name='forecastsnapshot',
            name='source_kind',
            field=models.CharField(
                choices=[('provider', 'Provider retrieval'), ('unknown', 'Legacy / unverified')],
                default='provider',
                max_length=10,
            ),
        ),
    ]
