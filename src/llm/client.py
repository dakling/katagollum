import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


class LLMProvider(Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    GOOGLE = "google"


@dataclass
class LLMConfig:
    provider: LLMProvider
    model: str
    base_url: str | None = None
    api_key: str | None = None
    temperature: float = 0.7
    max_tokens: int = 1024


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall]
    raw_response: Any


class OpenAICompatibleClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or "not-needed"
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.headers = {"Content-Type": "application/json"}
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"

    def _build_tools(self, tools: list[dict] | None) -> list[dict]:
        if not tools:
            return []
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters", {}),
                },
            }
            for t in tools
        ]

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            payload["tools"] = self._build_tools(tools)

        async with httpx.AsyncClient(timeout=600.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions", headers=self.headers, json=payload
            )
            response.raise_for_status()
            return response.json()

    async def chat_stream(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> AsyncGenerator[dict, None]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }
        if tools:
            payload["tools"] = self._build_tools(tools)

        async with httpx.AsyncClient(timeout=600.0) as client:
            async with client.stream(
                "POST", f"{self.base_url}/chat/completions", headers=self.headers, json=payload
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data != "[DONE]":
                            yield json.loads(data)


class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config
        self.client: OpenAICompatibleClient
        self._setup_client()

    def _setup_client(self) -> None:
        if self.config.base_url:
            base_url = self.config.base_url
        elif self.config.provider == LLMProvider.OLLAMA:
            base_url = "http://localhost:11434/v1"
        elif self.config.provider == LLMProvider.OPENAI:
            base_url = "https://api.openai.com/v1"
        else:
            base_url = "http://localhost:11434/v1"

        self.client = OpenAICompatibleClient(
            base_url=base_url,
            model=self.config.model,
            api_key=self.config.api_key,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        logger.info(
            "LLM client initialized",
            provider=self.config.provider.value,
            model=self.config.model,
            base_url=base_url,
        )

    def format_system_prompt(self, base_prompt: str, game_state: dict) -> str:
        board_size = game_state.get("board_size", 19)
        komi = game_state.get("komi", 7.5)
        player_color = game_state.get("player_color", "black")
        ai_color = "white" if player_color == "black" else "black"

        return f"""{base_prompt}

Current game state:
- Board size: {board_size}x{board_size}
- Komi: {komi}
- You play: {ai_color}
- User plays: {player_color}

Coordinate format: Use A19 notation (e.g., D4, Q16, T19).
Respond in an entertaining way - you have personality!
""".strip()

    async def chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        tools: list[dict] | None = None,
        game_state: dict | None = None,
    ) -> LLMResponse:
        formatted_system = self.format_system_prompt(system_prompt, game_state or {})
        all_messages = [{"role": "system", "content": formatted_system}] + messages

        try:
            response = await self.client.chat(all_messages, tools)

            choice = response["choices"][0]
            message = choice["message"]

            content = message.get("content", "") or ""
            tool_calls = []

            if "tool_calls" in message:
                for tc in message["tool_calls"]:
                    tool_calls.append(
                        ToolCall(
                            name=tc["function"]["name"],
                            arguments=json.loads(tc["function"]["arguments"]),
                        )
                    )

            return LLMResponse(content=content, tool_calls=tool_calls, raw_response=response)

        except httpx.HTTPStatusError as e:
            logger.error(
                "LLM API error",
                error=str(e),
                status_code=e.response.status_code,
                response_text=e.response.text[:500] if e.response.text else "",
            )
            raise
        except Exception as e:
            logger.error("LLM API error", error=str(e))
            raise

    async def close(self) -> None:
        pass


def create_llm_client(
    provider: str = "ollama",
    model: str = "llama3.2",
    base_url: str | None = None,
    api_key: str | None = None,
    temperature: float = 0.7,
) -> LLMClient:
    try:
        provider_enum = LLMProvider(provider.lower())
    except ValueError:
        logger.warning(f"Unknown provider {provider}, defaulting to ollama")
        provider_enum = LLMProvider.OLLAMA

    config = LLMConfig(
        provider=provider_enum,
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
    )

    return LLMClient(config)
