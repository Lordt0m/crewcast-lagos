from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_syncattempt_source_kind'),
    ]

    operations = [
        # Older demo seeds fabricated quota usage. Keep the reservation values
        # for cap enforcement, but do not present them as verified calls.
        migrations.AddField(
            model_name='budgetwindow',
            name='source_kind',
            field=models.CharField(
                choices=[('worker', 'Background worker'), ('unknown', 'Legacy / unverified')],
                default='unknown',
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name='budgetwindow',
            name='source_kind',
            field=models.CharField(
                choices=[('worker', 'Background worker'), ('unknown', 'Legacy / unverified')],
                default='worker',
                max_length=10,
            ),
        ),
    ]
