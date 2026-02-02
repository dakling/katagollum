import asyncio
import inspect
from collections.abc import Callable
from contextlib import AsyncExitStack
from typing import Any

import structlog
import uvicorn
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route

from .gtp_client import GTPClient, create_gtp_client
from ..config_loader import get_katago_model, get_katago_config

logger = structlog.get_logger(__name__)

mcp = FastMCP("KataGo")

gtp_client: GTPClient | None = None
exit_stack = AsyncExitStack()

BOARD_SIZE = 19
KOMI = 7.5
HANDICAP = 0

# Get KataGo paths from config file
KATAGO_MODEL = get_katago_model()
KATAGO_CONFIG = get_katago_config()
KATAGO_COMMAND = f"katago gtp -model {KATAGO_MODEL} -config {KATAGO_CONFIG}"


async def get_client() -> GTPClient:
    global gtp_client
    if gtp_client is None:
        raise RuntimeError("KataGo client not initialized")
    return gtp_client


async def _initialize_game(
    board_size: int, komi: float, handicap: int = 0, katago_command: str = ""
) -> str:
    global gtp_client, BOARD_SIZE, KOMI, HANDICAP

    BOARD_SIZE = board_size
    KOMI = komi
    HANDICAP = handicap

    if not katago_command:
        katago_command = KATAGO_COMMAND
    command = katago_command.split()

    gtp_client = await create_gtp_client(katago_command=command, board_size=board_size, komi=komi)

    # Place handicap stones if applicable
    handicap_stones = []
    if handicap > 0:
        logger.info(f"Placing {handicap} handicap stones")
        handicap_stones = await gtp_client.fixed_handicap(handicap)
        if not handicap_stones:
            logger.error(f"Failed to place handicap stones")
            raise RuntimeError(f"Failed to place {handicap} handicap stones")
        logger.info(f"Handicap stones placed at: {handicap_stones}")

        # Reset previous_score after handicap placement
        # After handicap stones, it's White's turn to move
        gtp_client.previous_score = await gtp_client.kata_analyze_normalized("W")
        logger.debug(
            f"Reset previous_score after handicap: {gtp_client.previous_score} (Black's perspective)"
        )

    name = await gtp_client.name()
    version = await gtp_client.version()

    result_msg = f"Game initialized with {name} {version} (board size: {board_size}, komi: {komi}"
    if handicap > 0:
        result_msg += f", handicap: {handicap} stones at {', '.join(handicap_stones)}"
    result_msg += ")"

    return result_msg


async def _get_final_score() -> dict:
    client = await get_client()
    score = await client.final_score()
    black_prisoners = await client.final_status_list("black_prisoners")
    white_prisoners = await client.final_status_list("white_prisoners")

    return {
        "score": score,
        "black_prisoners": len(black_prisoners),
        "white_prisoners": len(white_prisoners),
    }


def _parse_showboard_output(output: str, board_size: int) -> list[list[str]]:
    """Parse the showboard GTP output into a 2D board array."""
    lines = output.strip().split("\n")
    board = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line and (line[0].isdigit() or (len(line) > 1 and line[0].isdigit())):
            row = []
            i = 0
            while len(row) < board_size and i < len(line):
                char = line[i]
                if char in "BW":
                    row.append(char)
                elif char == ".":
                    row.append(".")
                i += 1
            while len(row) < board_size:
                row.append(".")
            if row:
                board.append(row)

    while len(board) < board_size:
        board.append(["."] * board_size)

    return board


async def _process_user_move(color: str, move: str) -> dict:
    """Process a user's move: commit it to the board and get KataGo's response.
    Returns the user's move and KataGo's recommended move, without verbose output.

    Score delta calculation:
    - All scores are normalized to Black's perspective (positive = Black lead)
    - previous_score: Black's lead before user's move
    - current_score: Black's lead after user's move
    - raw_delta = previous_score - current_score (positive means Black gained)
    - If user is White: negate the delta so positive = user lost points
    - Final: positive delta = bad move, negative delta = good move
    """
    client = await get_client()

    commit_result = await client.play(color, move)

    if commit_result:
        # Analyze position after user's move
        # Opponent is now to move, so pass their color for normalization
        opponent_color = "W" if color == "B" else "B"
        current_score = await client.kata_analyze_normalized(opponent_color)

        # Calculate raw score delta (both scores in Black's perspective)
        raw_delta = client.previous_score - current_score

        # Adjust for user's color:
        # - If user is Black: positive raw_delta = Black gained = bad for user
        # - If user is White: positive raw_delta = Black gained = good for user (so negate)
        if color == "W":
            score_delta = -raw_delta
        else:
            score_delta = raw_delta

        logger.debug(
            f"Score delta calculation: previous({client.previous_score}) - current({current_score}) = {raw_delta} "
            f"(user plays {color}) -> final delta: {score_delta}"
        )

        # Update previous_score for next turn
        client.previous_score = current_score

        # Generate KataGo's response
        katago_result = await client.genmove("W" if color == "B" else "B")

        return {
            "user_move": move,
            "commit_success": commit_result,
            "katago_move": katago_result.move,
            "score_delta": score_delta,
        }
    else:
        return {
            "user_move": "None",
            "commit_success": False,
            "katago_move": "None",
            "score_delta": 0.0,
        }


async def _make_first_move(user_color: str) -> dict:
    """Make the first move when LLM needs to start the game.

    Cases:
    1. Handicap = 0, user plays White: LLM (Black) moves first
    2. Handicap > 0, user plays Black: LLM (White) moves first after handicap stones

    Returns the move coordinate and a greeting message.
    """
    client = await get_client()

    # Determine which color LLM should play
    if HANDICAP == 0 and user_color == "W":
        # Normal game, user is White, so LLM (Black) moves first
        llm_color = "B"
        logger.info("First move: LLM playing Black in even game")
    elif HANDICAP > 0 and user_color == "B":
        # Handicap game, user is Black, so LLM (White) moves first
        llm_color = "W"
        logger.info(f"First move: LLM playing White after {HANDICAP} handicap stones")
    else:
        # User should move first
        logger.info("First move: User should move first")
        return {
            "move": None,
            "color": None,
            "message": None,
        }

    # Generate first move
    logger.info(f"Generating first move for {llm_color}")
    katago_result = await client.genmove(llm_color)

    if not katago_result.move:
        logger.error("Failed to generate first move")
        return {
            "move": None,
            "color": None,
            "message": "Failed to generate opening move",
        }

    # Analyze position after first move
    # After LLM's first move, it's user's turn
    client.previous_score = await client.kata_analyze_normalized(user_color)
    logger.debug(
        f"Set previous_score after first move: {client.previous_score} (Black's perspective)"
    )

    # Generate greeting based on game type
    if HANDICAP > 0:
        message = f"I'll start. I play {katago_result.move}. Let's see how you handle a {HANDICAP}-stone handicap!"
    else:
        message = f"I'll start. I play {katago_result.move}. Let's begin!"

    logger.info(f"First move generated: {llm_color} {katago_result.move}")

    return {
        "move": katago_result.move,
        "color": llm_color,
        "message": message,
    }


async def _get_server_info() -> dict:
    client = await get_client()
    return {
        "name": await client.name(),
        "version": await client.version(),
        "board_size": BOARD_SIZE,
        "komi": KOMI,
    }


def _func_to_tool(func: Callable, name: str, description: str) -> dict[str, Any]:
    """Convert a function to tool schema for the CLI."""
    sig = inspect.signature(func)
    properties = {}
    required = []

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "return"):
            continue

        param_type = "string"
        if param.annotation is bool:
            param_type = "boolean"
        elif param.annotation is int:
            param_type = "integer"
        elif param.annotation is float:
            param_type = "number"

        default = param.default if param.default is not inspect.Parameter.empty else None
        if default is not None and not isinstance(default, str | bool | int | float):
            continue

        properties[param_name] = {"type": param_type}
        if default is not None:
            properties[param_name]["default"] = default

        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def get_tool_definitions() -> list[dict[str, Any]]:
    """Generate tool definitions from server functions. Single source of truth."""
    return [
        _func_to_tool(
            _process_user_move,
            "process_user_move",
            "Process the user's move: commit it to the board, analyze it, and get KataGo's recommended response. Call this once per turn. Arguments: color (user's color, 'B' for Black or 'W' for White), move (user's move coordinate). Returns the user's move analysis and KataGo's response move.",
        ),
        _func_to_tool(_get_final_score, "get_final_score", "Get the final score of the game."),
    ]


@mcp.tool()
async def initialize_game(
    board_size: int = 19,
    komi: float = 7.5,
    handicap: int = 0,
    katago_command: str = "",
) -> str:
    # Use empty string default to trigger fallback to KATAGO_COMMAND from config
    return await _initialize_game(board_size, komi, handicap, katago_command)


@mcp.tool()
async def get_final_score() -> dict:
    return await _get_final_score()


@mcp.tool()
async def process_user_move(color: str, move: str) -> dict:
    return await _process_user_move(color, move)


@mcp.tool()
async def get_server_info() -> dict:
    return await _get_server_info()


@mcp.tool()
async def make_first_move(user_color: str) -> dict:
    return await _make_first_move(user_color)


async def handle_list_tools(request):
    """Return tool definitions for LLM tool calling."""
    tools = get_tool_definitions()
    return JSONResponse({"tools": tools})


async def handle_call_tool(request):
    try:
        data = await request.json()
        tool_name = data.get("name")
        arguments = data.get("arguments", {})

        tool_map = {
            "initialize_game": lambda: _initialize_game(
                arguments.get("board_size", BOARD_SIZE),
                arguments.get("komi", KOMI),
                arguments.get("handicap", 0),
                arguments.get("katago_command", KATAGO_COMMAND),
            ),
            "process_user_move": lambda: _process_user_move(
                arguments.get("color", "B"),
                arguments.get("move", ""),
            ),
            "get_final_score": _get_final_score,
            "get_server_info": _get_server_info,
            "make_first_move": lambda: _make_first_move(
                arguments.get("user_color", "B"),
            ),
        }

        if tool_name not in tool_map:
            return JSONResponse({"error": f"Unknown tool: {tool_name}"}, status_code=400)

        result = await tool_map[tool_name]()
        return JSONResponse({"result": result})

    except Exception as e:
        logger.error("Tool call error", error=str(e), exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


async def handle_board_state(request):
    """Handle requests for the current board state."""
    try:
        logger.info("Board state request received")
        client = await get_client()
        board_state = await client.list_board()
        logger.info(
            "Board state retrieved",
            board_size=board_state.get("board_size"),
            board_rows=len(board_state.get("board", [])),
            has_stones=bool(
                board_state.get("board")
                and any(any(cell != "." for cell in row) for row in board_state.get("board", []))
            ),
        )
        return JSONResponse({"result": board_state})
    except Exception as e:
        logger.error("Board state error", error=str(e), exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


async def run_stdio_server():
    async with exit_stack:
        await mcp.run_stdio_async()


def main():
    global KATAGO_COMMAND
    import argparse

    parser = argparse.ArgumentParser(description="KataGo MCP Server")
    parser.add_argument(
        "--transport", "-t", default="sse", choices=["stdio", "sse"], help="Transport type"
    )
    parser.add_argument("--host", "-H", default="localhost", help="Host for SSE transport")
    parser.add_argument("--port", "-p", type=int, default=3001, help="Port for SSE transport")
    parser.add_argument(
        "--katago-command",
        "-k",
        default=KATAGO_COMMAND,
        help=f"KataGo GTP command (default: {KATAGO_COMMAND})",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        KATAGO_COMMAND = args.katago_command
        app = Starlette(
            routes=[
                Route("/list_tools", handle_list_tools, methods=["GET"]),
                Route("/call_tool", handle_call_tool, methods=["POST"]),
                Route("/board_state", handle_board_state, methods=["GET"]),
            ]
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )
        config = uvicorn.Config(app, host=args.host, port=args.port, log_level="error")
        server = uvicorn.Server(config)
        server.run()
    else:
        asyncio.run(run_stdio_server())


if __name__ == "__main__":
    main()
