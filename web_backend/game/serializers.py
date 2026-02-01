from rest_framework import serializers
from .models import GameState, Move, ChatMessage


class MoveSerializer(serializers.ModelSerializer):
    class Meta:
        model = Move
        fields = ["id", "color", "coordinate", "move_number", "created_at"]


class GameStateSerializer(serializers.ModelSerializer):
    moves = MoveSerializer(many=True, read_only=True)

    class Meta:
        model = GameState
        fields = [
            "id",
            "board_size",
            "komi",
            "handicap",
            "user_color",
            "ai_color",
            "game_over",
            "persona",
            "created_at",
            "updated_at",
            "moves",
        ]
        read_only_fields = ["ai_color"]


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ["id", "game", "role", "content", "created_at"]
