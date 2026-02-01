import asyncio
import httpx
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
project_root = backend_dir.parent
sys.path.insert(0, str(project_root))

from game.models import GameState, Move, ChatMessage
from game.serializers import GameStateSerializer, MoveSerializer, ChatMessageSerializer

try:
    from src.go_game import process_turn_with_llm

    print("[VIEW] Successfully imported go_game module")
except ImportError as e:
    print(f"[VIEW] Failed to import go_game: {e}")
    process_turn_with_llm = None


MCP_URL = "http://localhost:3001"


class GameStateViewSet(viewsets.ModelViewSet):
    queryset = GameState.objects.all().order_by("-created_at")
    serializer_class = GameStateSerializer

    def create(self, request, *args, **kwargs):
        board_size = request.data.get("board_size", 19)
        komi = request.data.get("komi", 7.5)
        user_color = request.data.get("user_color", "B")
        persona = request.data.get("persona", "arrogant")

        game = GameState.objects.create(
            board_size=board_size,
            komi=komi,
            user_color=user_color,
            persona=persona,
        )

        return Response(GameStateSerializer(game).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def board(self, request, pk=None):
        game = self.get_object()
        moves = game.moves.all().order_by("move_number")
        board = self._build_board(game.board_size, moves)
        return Response(
            {
                "board_size": game.board_size,
                "komi": game.komi,
                "user_color": game.user_color,
                "ai_color": game.ai_color,
                "game_over": game.game_over,
                "board": board,
                "moves": MoveSerializer(moves, many=True).data,
            }
        )

    def _build_board(self, size, moves):
        board = [["." for _ in range(size)] for _ in range(size)]
        for move in moves:
            row, col = self._gtp_to_coords(move.coordinate, size)
            if row is not None:
                board[row][col] = move.color
        return board

    def _gtp_to_coords(self, gtp_coord, size):
        if gtp_coord.lower() == "pass":
            return None, None
        col = ord(gtp_coord[0].upper()) - ord("A")
        if col >= 8:
            col -= 1
        row = size - int(gtp_coord[1:])
        return row, col

    @action(detail=True, methods=["post"])
    def submit_move(self, request, pk=None):
        game = self.get_object()
        move_coord = request.data.get("coordinate")

        if not move_coord:
            return Response({"error": "Coordinate required"}, status=status.HTTP_400_BAD_REQUEST)

        move_number = game.moves.count() + 1
        user_color = game.user_color

        Move.objects.create(
            game=game,
            color=user_color,
            coordinate=move_coord,
            move_number=move_number,
        )

        chat_history = [
            {"role": m.role, "content": m.content}
            for m in game.chat_messages.all().order_by("created_at")[10:]
        ]

        print(f"[VIEW] Calling process_turn_with_llm for move: {move_coord}")
        result = asyncio.run(
            process_turn_with_llm(
                user_move=move_coord,
                chat_history=chat_history,
                persona=game.persona,
                board_size=game.board_size,
                komi=game.komi,
                user_color=game.user_color,
            )
        )
        print(f"[VIEW] Got result: {result[:100]}...")

        bot_response = result

        ChatMessage.objects.create(
            game=game,
            role="assistant",
            content=bot_response,
        )

        game.refresh_from_db()
        return Response(
            {
                "game": GameStateSerializer(game).data,
                "user_move": move_coord,
                "bot_response": bot_response,
            }
        )


class ChatViewSet(viewsets.ModelViewSet):
    queryset = ChatMessage.objects.all()
    serializer_class = ChatMessageSerializer

    def get_queryset(self):
        game_id = self.request.query_params.get("game_id")
        if game_id:
            return ChatMessage.objects.filter(game_id=game_id)
        return ChatMessage.objects.all()

    @action(detail=False, methods=["post"])
    def send_message(self, request):
        game_id = request.data.get("game_id")
        content = request.data.get("content")
        role = request.data.get("role", "user")

        if not game_id or not content:
            return Response(
                {"error": "game_id and content required"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            game = GameState.objects.get(id=game_id)
        except GameState.DoesNotExist:
            return Response({"error": "Game not found"}, status=status.HTTP_404_NOT_FOUND)

        if role == "user":
            chat_history = [
                {"role": m.role, "content": m.content}
                for m in game.chat_messages.all().order_by("created_at")[10:]
            ]

            print(f"[VIEW] Calling process_turn_with_llm for chat: {content[:50]}...")
            result = asyncio.run(
                process_turn_with_llm(
                    user_move=content,
                    chat_history=chat_history,
                    persona=game.persona,
                    board_size=game.board_size,
                    komi=game.komi,
                    user_color=game.user_color,
                )
            )

            bot_content = result if result else "..."

            user_msg = ChatMessage.objects.create(game=game, role="user", content=content)
            bot_msg = ChatMessage.objects.create(game=game, role="assistant", content=bot_content)

            return Response(
                {
                    "user_message": ChatMessageSerializer(user_msg).data,
                    "bot_message": ChatMessageSerializer(bot_msg).data,
                },
                status=status.HTTP_201_CREATED,
            )
        else:
            message = ChatMessage.objects.create(game=game, role=role, content=content)
            return Response(ChatMessageSerializer(message).data, status=status.HTTP_201_CREATED)


class InitializeGameView(APIView):
    def post(self, request):
        board_size = request.data.get("board_size", 19)
        komi = request.data.get("komi", 7.5)
        handicap = request.data.get("handicap", 0)
        user_color = request.data.get("user_color", "B")
        persona = request.data.get("persona", "arrogant")
        katago_command = request.data.get("katago_command")

        game = GameState.objects.create(
            board_size=board_size,
            komi=komi,
            handicap=handicap,
            user_color=user_color,
            persona=persona,
        )

        args = {"board_size": board_size, "komi": komi, "handicap": handicap}
        if katago_command:
            args["katago_command"] = katago_command

        try:
            with httpx.Client(timeout=30.0) as client:
                client.post(
                    f"{MCP_URL}/call_tool",
                    json={"name": "initialize_game", "arguments": args},
                )
        except Exception as e:
            print(f"[WARN] Failed to initialize KataGo: {e}")

        return Response(GameStateSerializer(game).data, status=status.HTTP_201_CREATED)


class FirstMoveView(APIView):
    def post(self, request, game_id):
        try:
            game = GameState.objects.get(id=game_id)
        except GameState.DoesNotExist:
            return Response({"error": "Game not found"}, status=status.HTTP_404_NOT_FOUND)

        # Determine if LLM should move first
        handicap = game.handicap
        user_color = game.user_color

        llm_should_move = (handicap == 0 and user_color == "W") or (
            handicap > 0 and user_color == "B"
        )

        if not llm_should_move:
            # User should move first
            board = self._get_board_from_katago()
            return Response(
                {
                    "move": None,
                    "color": None,
                    "message": None,
                    "board_state": board,
                }
            )

        # Call MCP to make first move
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    f"{MCP_URL}/call_tool",
                    json={"name": "make_first_move", "arguments": {"user_color": user_color}},
                )
                result = response.json().get("result", {})

                # Save the move to database
                if result.get("move"):
                    Move.objects.create(
                        game=game,
                        color=result["color"],
                        coordinate=result["move"],
                        move_number=1,
                    )

                # Get updated board from KataGo (includes handicap stones)
                board = self._get_board_from_katago()

                return Response(
                    {
                        "move": result.get("move"),
                        "color": result.get("color"),
                        "message": result.get("message"),
                        "board_state": board,
                    }
                )
        except Exception as e:
            print(f"[ERROR] Failed to make first move: {e}")
            return Response(
                {
                    "error": str(e),
                    "move": None,
                    "color": None,
                    "message": "Failed to generate first move",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _get_board(self, game):
        moves = game.moves.all().order_by("move_number")
        size = game.board_size
        board = [["." for _ in range(size)] for _ in range(size)]

        for move in moves:
            col = ord(move.coordinate[0].upper()) - ord("A")
            if col >= 8:
                col -= 1
            row = size - int(move.coordinate[1:])
            if 0 <= row < size and 0 <= col < size:
                board[row][col] = move.color

        return {
            "board_size": size,
            "komi": game.komi,
            "handicap": game.handicap,
            "user_color": game.user_color,
            "ai_color": game.ai_color,
            "game_over": game.game_over,
            "board": board,
            "moves": MoveSerializer(moves, many=True).data,
        }

    def _get_board_from_katago(self):
        """Fetch the actual board state from KataGo, including handicap stones."""
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(f"{MCP_URL}/board_state")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("result"):
                        return {
                            "board_size": data["result"].get("board_size", 19),
                            "board": data["result"].get("board", []),
                        }
        except Exception as e:
            print(f"[ERROR] Failed to fetch board from KataGo: {e}")

        # Fallback to empty board
        return {
            "board_size": 19,
            "board": [["." for _ in range(19)] for _ in range(19)],
        }
