import uuid

from django.db import migrations, models


def populate_invitation_tokens(apps, schema_editor):
    GameInvitation = apps.get_model('games', 'GameInvitation')

    for invitation in GameInvitation.objects.filter(token__isnull=True):
        invitation.token = uuid.uuid4()
        invitation.save(update_fields=['token'])


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0011_alter_gameinvitation_opponent_mode'),
    ]

    operations = [
        migrations.AddField(
            model_name='gameinvitation',
            name='token',
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(populate_invitation_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='gameinvitation',
            name='token',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
