from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0008_chessgame_rating_applied'),
    ]

    operations = [
        migrations.AddField(
            model_name='chessgame',
            name='active_clock_color',
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(
            model_name='chessgame',
            name='black_time_seconds',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='chessgame',
            name='clock_started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='chessgame',
            name='time_control_minutes',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='chessgame',
            name='white_time_seconds',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='gameinvitation',
            name='time_control_minutes',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
