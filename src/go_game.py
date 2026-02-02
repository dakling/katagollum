import asyncio
import os
from pathlib import Path
from typing import Any

import httpx
import yaml

from src.llm.client import LLMClient, LLMConfig, LLMProvider, ToolCall
from src.config_loader import get_llm_model, get_llm_base_url


LLM_BASE_URL = get_llm_base_url()
LLM_MODEL = get_llm_model()
MCP_URL = os.getenv("MCP_URL", "http://localhost:3001")


def normalize_tool_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Normalize tool call arguments for validation."""
    normalized = arguments.copy()

    # Normalize color
    color = normalized.get("color", "").strip().lower()
    if color in ["black", "b"]:
        normalized["color"] = "B"
    elif color in ["white", "w"]:
        normalized["color"] = "W"
    else:
        normalized["color"] = normalized.get("color", "").strip().upper()

    # Normalize move
    move = normalized.get("move", "").strip().upper()
    move = "".join(c for c in move if c.isalnum())  # Remove non-alphanumeric
    normalized["move"] = move

    return normalized


def validate_move_format(move: str) -> bool:
    """Validate that a move coordinate is in the correct format."""
    if not move or len(move) < 2:
        return False

    move = move.upper().strip()

    # Check first character is A-H or J-T (excluding I)
    col = move[0]
    if col == "I" or col < "A" or col > "T":
        return False

    # Check remaining characters form a number 1-19
    try:
        row = int(move[1:])
        if row < 1 or row > 19:
            return False
    except ValueError:
        return False

    return True


def validate_tool_arguments(tool_name: str, arguments: dict[str, Any]) -> tuple[bool, str]:
    """Validate tool call arguments."""
    if tool_name != "process_user_move":
        return True, ""

    normalized = normalize_tool_arguments(arguments)
    color = normalized["color"]
    move = normalized["move"]

    if color not in ["B", "W"]:
        return (
            False,
            f"Invalid color '{arguments.get('color', '')}'. Must be 'B', 'W', 'black', or 'white'.",
        )

    if not validate_move_format(move):
        return (
            False,
            f"Invalid move format '{arguments.get('move', '')}'. Must be letter A-T (excluding I) followed by number 1-19.",
        )

    return True, ""


def get_llm_client() -> LLMClient:
    """Get or create a shared LLM client."""
    config = LLMConfig(
        provider=LLMProvider.OLLAMA,
        model=LLM_MODEL,
        base_url=LLM_BASE_URL,
    )
    return LLMClient(config)


def load_persona(persona_name: str) -> str:
    """Load persona from YAML file."""
    persona_file = Path(__file__).parent.parent / "prompts" / "personas.yaml"
    if persona_file.exists():
        with open(persona_file) as f:
            data = yaml.safe_load(f)
            game_flow = data.get("game_flow", "").strip()
            personas = data.get("personas", {})
            if persona_name in personas:
                style = personas[persona_name].get("style", "").strip()
                return f"{game_flow}\n\n{style}"
    return "You are a Go-playing AI with personality. Be entertaining."


def get_tool_definitions() -> list[dict[str, Any]]:
    """Get tool definitions from MCP server."""
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{MCP_URL}/list_tools")
            if response.status_code == 200:
                return response.json().get("tools", [])
    except Exception:
        pass
    return []


def call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Call an MCP tool synchronously."""
    try:
        with httpx.Client(timeout=600.0) as client:
            response = client.post(
                f"{MCP_URL}/call_tool",
                json={"name": tool_name, "arguments": arguments},
            )
            return response.json().get("result", {})
    except Exception as e:
        return {"error": str(e)}


async def call_mcp_tool_async(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Call an MCP tool asynchronously."""
    async with httpx.AsyncClient(timeout=600.0) as client:
        response = await client.post(
            f"{MCP_URL}/call_tool",
            json={"name": tool_name, "arguments": arguments},
        )
        return response.json().get("result", {})


async def process_turn_with_llm(
    user_move: str,
    chat_history: list[dict[str, str]],
    persona: str,
    board_size: int = 19,
    komi: float = 6.5,
    user_color: str = "B",
    mcp_url: str = MCP_URL,
) -> dict[str, str | None]:
    """Process a game turn using the same logic as CLI's GoGame._process_turn_via_llm.

    Returns:
        dict with keys:
            - response: str - The LLM's text response
            - ai_move: str | None - The AI's move coordinate (e.g., "D4") or None if no move
    """
    print(
        f"[PROCESS_TURN] Processing turn: user_move={user_move}, persona={persona}, user_color={user_color}"
    )

    game_state = {"board_size": board_size, "komi": komi, "player_color": user_color}
    tools = get_tool_definitions()
    print(f"[PROCESS_TURN] Found {len(tools)} tools from MCP server")

    # Track the AI's move
    ai_move = None

    if not tools:
        print("[PROCESS_TURN] WARNING: No tools found from MCP server!")
        return {"response": "Error: Could not connect to MCP server for tool definitions.", "ai_move": None}

    messages = chat_history.copy()
    messages.append({"role": "user", "content": f"My move: {user_move}"})

    # Store original user message for move validation
    original_user_message = user_move.lower()

    system_prompt = load_persona(persona)

    llm_client = get_llm_client()

    print(f"[PROCESS_TURN] Calling LLM with {len(tools)} tools...")
    response = await llm_client.chat(
        messages=messages,
        system_prompt=system_prompt,
        tools=tools,
        game_state=game_state,
    )

    print(
        f"[PROCESS_TURN] LLM response: {len(response.content)} chars, tool_calls: {len(response.tool_calls)}"
    )

    tool_calls = response.tool_calls

    if not tool_calls:
        print(f"[PROCESS_TURN] No tool calls found. Response: {response.content[:200]}...")
        # If no tool calls, just return the conversational response
        return {"response": response.content or "I have nothing to say.", "ai_move": None}

    # Process tool calls (should only be process_user_move for actual moves)
    print(f"[PROCESS_TURN] Processing {len(tool_calls)} tool call(s)")
    for tc in tool_calls:
        tool_name = tc.name if isinstance(tc, ToolCall) else tc["name"]
        arguments = tc.arguments if isinstance(tc, ToolCall) else tc.get("arguments", {})

        # Check if move coordinate actually appeared in user's message
        move_coord = arguments.get("move", "").lower()
        if move_coord and move_coord not in original_user_message:
            print(
                f"[PROCESS_TURN] Move {move_coord} not found in user message: {original_user_message}"
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_name": tool_name,
                    "content": "Error: The user did not provide this move coordinate. Please respond conversationally instead.",
                }
            )
            print(f"[PROCESS_TURN] Calling LLM after move validation error...")
            response = await llm_client.chat(
                messages=messages,
                system_prompt=system_prompt,
                tools=[],
                game_state=game_state,
            )
            print(f"[PROCESS_TURN] Final response after error: {response.content[:100]}...")
            return {"response": response.content or "I have nothing to say.", "ai_move": None}

        # Validate tool arguments before executing
        is_valid, error_message = validate_tool_arguments(tool_name, arguments)
        if not is_valid:
            print(f"[PROCESS_TURN] Invalid tool arguments: {error_message}")
            # Add error as tool result so LLM can see it and respond appropriately
            messages.append(
                {
                    "role": "tool",
                    "tool_name": tool_name,
                    "content": f"Error: {error_message}. No move was played. Please respond conversationally instead.",
                }
            )
            # Get LLM response after seeing the error
            print(f"[PROCESS_TURN] Calling LLM after validation error...")
            response = await llm_client.chat(
                messages=messages,
                system_prompt=system_prompt,
                tools=[],
                game_state=game_state,
            )
            print(f"[PROCESS_TURN] Final response after error: {response.content[:100]}...")
            return {"response": response.content or "I have nothing to say.", "ai_move": None}

        # Normalize arguments before executing
        normalized_arguments = normalize_tool_arguments(arguments)
        print(f"[PROCESS_TURN] Calling MCP tool: {tool_name}({normalized_arguments})")
        result = await call_mcp_tool_async(tool_name, normalized_arguments)
        print(f"[PROCESS_TURN] MCP result: {str(result)[:200]}...")

        # Format result for LLM - simple and direct
        if isinstance(result, dict) and result.get("commit_success"):
            katago_move = result.get("katago_move", "PASS")
            ai_move = katago_move  # Track for return value
            score_delta = result.get("score_delta", 0.0)

            # Convert score delta to quality rating (matching prompt definitions)
            if score_delta < 0:
                quality = "great"
            elif score_delta <= 0.5:
                quality = "good"
            elif score_delta <= 3:
                quality = "small mistake"
            elif score_delta <= 5:
                quality = "medium mistake"
            elif score_delta <= 10:
                quality = "big mistake"
            else:
                quality = "terrible move"

            llm_content = f"The user played a {quality}. You play {katago_move}."
        else:
            llm_content = "The move failed."

        messages.append(
            {
                "role": "tool",
                "tool_name": tool_name,
                "content": llm_content,
            }
        )

    # Get final response after tool execution
    print(f"[PROCESS_TURN] Calling LLM for final response...")
    response = await llm_client.chat(
        messages=messages,
        system_prompt=system_prompt,
        tools=[],
        game_state=game_state,
    )

    print(f"[PROCESS_TURN] Final response: {response.content[:100]}..., ai_move: {ai_move}")
    return {"response": response.content or "I play PASS.", "ai_move": ai_move}
