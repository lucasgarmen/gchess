from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0009_chessgame_clock_gameinvitation_time_control'),
    ]

    operations = [
        migrations.AddField(
            model_name='chessgame',
            name='draw_offer_by_color',
            field=models.CharField(blank=True, max_length=10),
        ),
    ]
