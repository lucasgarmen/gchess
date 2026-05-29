import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import ChessGame
from .realtime import game_group_name
from .views import (
    GameActionError,
    game_access_filter,
    player_color_for_game,
    save_chat_message_for_user,
    save_move_for_user,
    touch_presence,
)

logger = logging.getLogger(__name__)


class GameConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.game_id = int(self.scope['url_route']['kwargs']['game_id'])
        self.group_name = game_group_name(self.game_id)
        self.user = self.scope.get('user')
        session = self.scope.get('session') or {}
        self.guest_id = session.get('guest_id')
        self.guest_name = session.get('guest_name', '')

        if not (self.user and self.user.is_authenticated) and not self.guest_id:
            await self.close(code=4001)
            return

        if not await self.user_can_access_game():
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({
            'type': 'connection.ready',
            'game_id': self.game_id,
        })

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        message_type = content.get('type')

        try:
            if message_type == 'move.create':
                await self.create_move(content.get('move') or {})
            elif message_type == 'chat.send':
                await self.send_chat_message(content.get('text'))
            elif message_type == 'ping':
                await self.send_json({'type': 'pong'})
            else:
                await self.send_error('Tipo de mensagem desconhecido.', status=400)
        except GameActionError as exc:
            await self.send_error(exc.payload.get('error', exc.message), status=exc.status)
        except Exception:
            logger.exception("WebSocket error for game %s and actor %s.", self.game_id, self.actor_label)
            await self.send_error('Erro inesperado no WebSocket.', status=500)

    async def create_move(self, move_data):
        result = await save_move_async(self.game_id, self.user, move_data, self.guest_id)

        logger.info(
            "Move saved through WebSocket for game %s; broadcasting to group %s.",
            self.game_id,
            self.group_name,
        )
        await self.channel_layer.group_send(self.group_name, {
            'type': 'move_created',
            'actor_id': self.actor_id,
            'actor_guest_id': self.guest_id or '',
            'result': result,
        })

    async def send_chat_message(self, text):
        message = await save_chat_message_async(self.game_id, self.user, text, self.guest_id, self.guest_name)

        await self.channel_layer.group_send(self.group_name, {
            'type': 'chat_message',
            'message': message,
        })

    async def move_created(self, event):
        await self.send_json({
            'type': 'move.created',
            'actor_id': event['actor_id'],
            'actor_guest_id': event.get('actor_guest_id', ''),
            'result': event['result'],
            'state': event['result'].get('state'),
        })

    async def chat_message(self, event):
        message = dict(event['message'])

        if self.actor_id:
            message['mine'] = message.get('sender_id') == self.actor_id
        elif self.guest_id:
            message['mine'] = message.get('sender_guest_id') == self.guest_id

        await self.send_json({
            'type': 'chat.message',
            'message': message,
        })

    async def send_error(self, message, status=400):
        await self.send_json({
            'type': 'error',
            'status': status,
            'error': message,
        })

    @database_sync_to_async
    def user_can_access_game(self):
        touch_presence(self.user)
        try:
            game = get_object_or_404(
                ChessGame,
                game_access_filter(self.user, self.guest_id),
                id=self.game_id,
            )
        except Http404:
            return False
        return bool(player_color_for_game(game, self.user, self.guest_id))

    @property
    def actor_id(self):
        if self.user and self.user.is_authenticated:
            return self.user.id
        return None

    @property
    def actor_label(self):
        return self.actor_id or f'guest:{self.guest_id or "unknown"}'


@database_sync_to_async
def save_move_async(game_id, user, move_data, guest_id=None):
    touch_presence(user)
    return save_move_for_user(game_id, user, move_data, guest_id)


@database_sync_to_async
def save_chat_message_async(game_id, user, text, guest_id=None, guest_name=''):
    touch_presence(user)
    message = save_chat_message_for_user(game_id, user, text, guest_id, guest_name)
    return {
        'id': message.id,
        'sender': message.sender.username if message.sender_id else message.sender_guest_name or 'Invitado',
        'sender_id': message.sender_id,
        'sender_guest_id': message.sender_guest_id,
        'text': message.text,
        'created_at': timezone.localtime(message.created_at).strftime('%H:%M'),
    }
