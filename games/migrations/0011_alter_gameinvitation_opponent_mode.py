from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0010_chessgame_draw_offer_by_color'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gameinvitation',
            name='opponent_mode',
            field=models.CharField(choices=[('direct', 'Oponente escolhido'), ('link', 'Convite por link'), ('random', 'Oponente aleatório')], max_length=20),
        ),
    ]
