import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def game_group_name(game_id):
    return f'game_{int(game_id)}'


def user_actor_id(user):
    if user and user.is_authenticated:
        return user.id
    return None


def broadcast_move_created(game_id, user, result, guest_id=None):
    channel_layer = get_channel_layer()

    if channel_layer is None:
        logger.warning("Move broadcast skipped for game %s: no channel layer configured.", game_id)
        return False

    group_name = game_group_name(game_id)
    event = {
        'type': 'move_created',
        'actor_id': user_actor_id(user),
        'actor_guest_id': guest_id or '',
        'result': result,
    }

    try:
        async_to_sync(channel_layer.group_send)(group_name, event)
    except Exception:
        logger.exception("Move broadcast failed for game %s group %s.", game_id, group_name)
        return False

    logger.info(
        "Move broadcast sent for game %s group %s move_id=%s move_count=%s.",
        game_id,
        group_name,
        result.get('move_id'),
        result.get('state', {}).get('move_count'),
    )
    return True
