import asyncio
from pathlib import Path
from typing import Any

import httpx
import yaml

from ..game.board import BoardState, Color, Move, gtp_to_a19, parse_move
from ..llm.client import LLMClient, LLMConfig, LLMProvider, ToolCall
from ..go_game import (
    process_turn_with_llm,
    load_persona as shared_load_persona,
    get_llm_client,
    get_tool_definitions,
    call_mcp_tool_async,
)

MCP_URL = "http://localhost:3001"


def validate_move(input_str: str, board: BoardState) -> str | None:
    """Validate and normalize user input. Returns GTP coordinate or None if invalid."""
    input_str = input_str.strip()

    if input_str.lower() in ["pass", "p"]:
        return "pass"

    if input_str.lower() in ["quit", "exit", "q"]:
        return "quit"

    move = parse_move(input_str, board)
    if move is None:
        return None

    if move.pass_move:
        return "pass"

    if move.resignation:
        return "resign"

    return move.coordinate


def format_move_for_llm(gtp_coord: str, board_size: int) -> str:
    """Convert GTP coordinate to A19 format for the LLM."""
    if gtp_coord.lower() == "pass":
        return "pass"
    return gtp_to_a19(gtp_coord, board_size).upper()


class GoGame:
    def __init__(
        self,
        llm_client: LLMClient,
        board: BoardState,
        persona: str = "sarcastic",
        mcp_url: str = MCP_URL,
        katago_command: str | None = None,
    ):
        self.llm = llm_client
        self.board = board
        self.mcp_url = mcp_url
        self.katago_command = katago_command
        self.persona = self._load_persona(persona)
        self.mcp_tools: list[dict[str, Any]] = []
        self.messages: list[dict] = []
        self.game_over = False

    def _load_persona(self, name: str) -> str:
        return shared_load_persona(name)

    def _get_ai_color(self) -> str:
        return self.board.ai_color().value

    def _get_user_color(self) -> str:
        return self.board.user_color().value

    async def _fetch_tool_definitions(self) -> list[dict[str, Any]]:
        """Fetch tool definitions from MCP server. Single source of truth."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{self.mcp_url}/list_tools", timeout=10.0)
                if response.status_code == 200:
                    data = response.json()
                    return data.get("tools", [])
            except Exception as e:
                print(f"[WARNING] Could not fetch tool definitions: {e}")
        return []

    async def _mcp_call(self, tool_name: str, arguments: dict) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.mcp_url}/call_tool",
                json={"name": tool_name, "arguments": arguments},
                timeout=600.0,
            )
            result = response.json()
            return result.get("result", {})

    async def _mcp_initialize(self, board_size: int, komi: float) -> str:
        args = {"board_size": board_size, "komi": komi}
        if self.katago_command:
            args["katago_command"] = self.katago_command
        result = await self._mcp_call("initialize_game", args)
        return result if isinstance(result, str) else str(result)

    async def _handle_tool_calls(self, tool_calls: list[ToolCall] | list[dict]) -> None:
        """Execute tool calls and add results to messages."""
        for tool_call in tool_calls:
            if isinstance(tool_call, dict):
                tool_name = tool_call.get("name") or ""
                arguments = tool_call.get("arguments", {})
            else:
                tool_name = tool_call.name
                arguments = tool_call.arguments
            if not tool_name:
                continue
            result = await self._mcp_call(tool_name, arguments)
            self.messages.append(
                {
                    "role": "tool",
                    "tool_name": tool_name,
                    "content": str(result),
                }
            )

    async def _get_user_input(self) -> str:
        """Get user input via stdin."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, input, "\nYour move: ")

    async def start(self) -> None:
        user_color = self._get_user_color()
        ai_color = self._get_ai_color()

        print(f"\n{'=' * 50}")
        print("   TRASH-TALK GO BOT")
        print(f"{'=' * 50}")
        print(f"Board size: {self.board.size}x{self.board.size}")
        print(f"Komi: {self.board.komi}")
        print(f"You play: {user_color}")
        print(f"Bot plays: {ai_color}")
        print(f"{'=' * 50}\n")

        print("Initializing KataGo (this takes ~15 seconds on first run)...")
        init_task = asyncio.create_task(self._mcp_initialize(self.board.size, self.board.komi))

        print("Fetching tool definitions from server...")
        self.mcp_tools = await self._fetch_tool_definitions()

        await init_task

        await self._game_loop()

    async def _process_turn_via_llm(self, user_move: str) -> None:
        """Process a game turn using the shared go_game module."""
        self.messages.append({"role": "user", "content": f"My move: {user_move}"})

        user_color = self._get_user_color()
        ai_color = self._get_ai_color()
        game_state = {
            "board_size": self.board.size,
            "komi": self.board.komi,
            "player_color": user_color,
        }

        response_text = await process_turn_with_llm(
            user_move=user_move,
            chat_history=self.messages,
            persona=self.persona,
            board_size=self.board.size,
            komi=self.board.komi,
            user_color=user_color,
            mcp_url=self.mcp_url,
        )

        print(f"\nBot: {response_text}")
        self.messages.append({"role": "assistant", "content": response_text})

    async def _game_loop(self) -> None:
        while not self.game_over:
            user_input = await self._get_user_input()
            move = validate_move(user_input, self.board)

            if move == "quit":
                print("Thanks for playing!")
                break

            if move is None:
                print("Invalid move. Try again.")
                continue

            await self._process_turn_via_llm(move)


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Trash-Talk Go Bot")
    parser.add_argument(
        "--persona",
        "-p",
        default="sarcastic",
        choices=["sarcastic", "arrogant", "encouraging", "chill", "competitive"],
        help="Bot personality",
    )
    parser.add_argument("--board-size", "-s", type=int, default=19, help="Board size")
    parser.add_argument("--komi", "-k", type=float, default=7.5, help="Komi")
    parser.add_argument("--model", "-m", default="llama3.2", help="LLM model")
    parser.add_argument("--provider", default="ollama", help="LLM provider")
    parser.add_argument("--base-url", help="LLM base URL")
    parser.add_argument("--mcp-url", default="http://localhost:3001", help="MCP server URL")
    parser.add_argument("--katago-command", help="KataGo GTP command")

    args = parser.parse_args()

    board = BoardState(size=args.board_size, komi=args.komi)

    try:
        provider = LLMProvider(args.provider.lower())
    except ValueError:
        provider = LLMProvider.OLLAMA

    llm_config = LLMConfig(provider=provider, model=args.model, base_url=args.base_url)
    llm_client = LLMClient(llm_config)

    mcp_url = args.mcp_url
    if not mcp_url.startswith("http://") and not mcp_url.startswith("https://"):
        mcp_url = f"http://{mcp_url}"

    game = GoGame(llm_client, board, args.persona, mcp_url, args.katago_command)

    try:
        await game.start()
    except KeyboardInterrupt:
        print("\nGame interrupted. Thanks for playing!")
    finally:
        await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
