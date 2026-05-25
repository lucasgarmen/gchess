from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0014_chessgame_black_guest_id_chessgame_is_rated_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='DailyVisit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('visits', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'visita diaria',
                'verbose_name_plural': 'visitas diarias',
                'ordering': ['-date'],
            },
        ),
    ]
