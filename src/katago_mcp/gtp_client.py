import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import structlog

from ..config_loader import get_katago_model, get_katago_config

logger = structlog.get_logger(__name__)


def expand_path(path: str) -> str:
    if path.startswith("~"):
        return str(Path(path).expanduser())
    return path


@dataclass
class GTPResponse:
    success: bool
    response: str
    message: str


@dataclass
class MoveResult:
    move: str
    score_delta: float | None = None
    raw_response: str = ""


class GTPClient:
    def __init__(self, katago_command: list[str] | None = None, config: dict | None = None):
        if katago_command is None:
            # Get paths from config file
            model_path = get_katago_model()
            config_path = get_katago_config()
            katago_command = [
                "katago",
                "gtp",
                "-model",
                model_path,
                "-config",
                config_path,
            ]
        self.command = katago_command
        self.config = config or {}
        self.process: asyncio.subprocess.Process | None = None
        self.command_id = 0
        self._initialized = False
        self.previous_score: float = (
            0.0  # Normalized score: positive = Black lead, negative = White lead
        )

    async def _drain_initialization(self) -> None:
        """Wait for KataGo to finish initialization by reading stderr."""
        if not self.process or not self.process.stderr:
            return

        logger.debug("Draining KataGo initialization...")
        while True:
            try:
                line = await asyncio.wait_for(self.process.stderr.readline(), timeout=30.0)
                if not line:
                    break
                decoded = line.decode().strip()
                if decoded:
                    logger.debug("KataGo init", line=decoded[:100])
                    if "GTP ready" in decoded:
                        logger.info("KataGo initialization complete")
                        break
            except TimeoutError:
                logger.warning("Timeout waiting for KataGo initialization")
                break
            except asyncio.CancelledError:
                break

    async def start(self) -> None:
        env = {}
        for key, value in self.config.items():
            env[f"KATAGO_{key.upper()}"] = str(value)

        expanded_command = [expand_path(arg) for arg in self.command]
        logger.info("Starting KataGo process", command=" ".join(expanded_command))

        self.process = await asyncio.create_subprocess_exec(
            *expanded_command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        await self._drain_initialization()
        self._initialized = True

    async def stop(self) -> None:
        if self.process:
            self.process.terminate()
            await self.process.wait()
            logger.info("Stopped KataGo process")

    async def send_command(self, *args: str, timeout: float = 10.0) -> GTPResponse:
        if not self.process:
            return GTPResponse(False, "", "Process not started")

        if not self._initialized:
            return GTPResponse(False, "", "KataGo not initialized")

        self.command_id += 1
        cmd_id = str(self.command_id)
        full_command = f"{cmd_id} {' '.join(args)}\n"

        logger.debug("Sending GTP command", command=full_command.strip())
        self.process.stdin.write(full_command.encode())
        await self.process.stdin.drain()

        command_name = args[0] if args else "unknown"
        is_analyze = command_name == "kata-analyze"

        all_lines = []
        response_line = None
        stdout_lines_read = 0
        stderr_lines_read = 0
        response_found = asyncio.Event()

        async def read_stdout() -> str | None:
            """Read stdout until we find the response line for this command."""
            nonlocal stdout_lines_read, response_line
            score_means = []
            max_score_means = 10
            max_total_lines = 100
            exit_reason = "timeout"

            try:
                while True:
                    # After response found, use shorter timeout to finish reading
                    if response_found.is_set():
                        # For kata-analyze, check if we have enough scoreMean values
                        if is_analyze and len(score_means) >= max_score_means:
                            exit_reason = f"collected {max_score_means} scoreMean values"
                            logger.debug(f"kata-analyze: early exit - {exit_reason}")
                            break
                        # Safety limit only for kata-analyze (other commands need unlimited lines)
                        if is_analyze and stdout_lines_read >= max_total_lines:
                            exit_reason = f"hit safety limit ({max_total_lines} lines)"
                            logger.debug(f"{command_name}: {exit_reason}")
                            break
                        try:
                            line = await asyncio.wait_for(
                                self.process.stdout.readline(), timeout=0.5
                            )
                        except asyncio.TimeoutError:
                            # Timeout after response is expected - we're done
                            exit_reason = "timeout after response"
                            break
                    else:
                        line = await asyncio.wait_for(
                            self.process.stdout.readline(), timeout=timeout
                        )

                    if not line:
                        exit_reason = "empty line (EOF)"
                        break

                    stdout_lines_read += 1
                    decoded = line.decode().strip()

                    if not decoded:
                        continue

                    # Check if this is our response line
                    if decoded.startswith(f"={cmd_id}") or decoded.startswith(f"?{cmd_id}"):
                        response_line = decoded
                        response_found.set()
                        logger.debug(
                            "GTP response line",
                            line=decoded[:100] if len(decoded) > 100 else decoded,
                        )
                        # Don't return - continue reading to capture more output
                        continue

                    # For analyze commands, store all lines and extract scoreMean
                    if is_analyze:
                        if len(decoded) > 500:
                            decoded = decoded[:500] + "...(truncated)"
                        all_lines.append(decoded)

                        # Try to extract scoreMean for early termination
                        if "scoreMean" in decoded and len(score_means) < max_score_means:
                            parts = decoded.split()
                            for i, part in enumerate(parts):
                                if part == "scoreMean" and i + 1 < len(parts):
                                    try:
                                        score_value = float(parts[i + 1])
                                        score_means.append(score_value)
                                        logger.debug(
                                            f"kata-analyze: extracted scoreMean #{len(score_means)}: {score_value}"
                                        )
                                        break
                                    except ValueError:
                                        continue
                    elif not decoded.startswith("info move"):
                        # Only store non-info lines for non-analyze commands
                        if len(decoded) > 500:
                            decoded = decoded[:500] + "...(truncated)"
                        all_lines.append(decoded)

                    # Log interesting lines
                    if stdout_lines_read <= 5 or (is_analyze and "scoreMean" in decoded):
                        logger.debug(
                            "GTP stdout",
                            line=decoded[:100] if len(decoded) > 100 else decoded,
                        )

            except asyncio.TimeoutError:
                if not response_found.is_set():
                    logger.warning(f"Timeout reading stdout for command {cmd_id}")
                exit_reason = "timeout"
            except Exception as e:
                logger.warning(f"Error reading stdout: {e}")
                exit_reason = f"exception: {e}"

            logger.debug(
                f"{command_name}: finished reading stdout ({stdout_lines_read} lines, exit: {exit_reason})"
            )
            return response_line

        async def read_stderr() -> None:
            """Read stderr for analyze commands to capture scoreMean info."""
            nonlocal stderr_lines_read
            if not is_analyze:
                return

            try:
                while stderr_lines_read < 500:  # Read up to 500 stderr lines
                    # Check if we should stop
                    if response_found.is_set() and stderr_lines_read > 50:
                        # After response found, read a bit more then stop
                        break

                    try:
                        line = await asyncio.wait_for(self.process.stderr.readline(), timeout=0.3)
                    except asyncio.TimeoutError:
                        # If response is found and we timeout, we're done
                        if response_found.is_set():
                            break
                        continue

                    if not line:
                        break

                    stderr_lines_read += 1
                    decoded = line.decode().strip()

                    if not decoded:
                        continue

                    # Capture stderr lines with scoreMean
                    if "scoreMean" in decoded:
                        if len(decoded) > 500:
                            decoded = decoded[:500] + "...(truncated)"
                        all_lines.append(decoded)
                        logger.debug(
                            "GTP stderr scoreMean",
                            line=decoded[:100] if len(decoded) > 100 else decoded,
                        )

            except Exception:
                pass

        try:
            if is_analyze:
                # For analyze, read both streams concurrently
                await asyncio.gather(read_stdout(), read_stderr())
            else:
                # For other commands, just read stdout
                await read_stdout()

        except TimeoutError:
            logger.warning("GTP command timed out", command=full_command.strip())
            return GTPResponse(False, "", "Command timed out")
        except Exception as e:
            logger.warning("GTP command failed with exception", error=str(e))
            return GTPResponse(False, "", f"Command failed: {str(e)}")

        if not response_line:
            return GTPResponse(False, "", "No response from GTP")

        success = response_line.startswith(f"={cmd_id}")

        if success:
            parts = response_line.split(None, 1)
            response = parts[1] if len(parts) > 1 else ""
        else:
            response = ""

        message_lines = [line for line in all_lines if line != response_line]
        message = "\n".join(message_lines)

        if not message:
            message = response_line

        logger.debug(
            "GTP response",
            command=command_name,
            cmd_id=cmd_id,
            success=success,
            response=response[:50] if response else "empty",
            message_len=len(message),
            stdout_lines=stdout_lines_read,
            stderr_lines=stderr_lines_read,
        )
        return GTPResponse(success, response, message)

    async def name(self) -> str:
        result = await self.send_command("name")
        return result.response if result.success else "unknown"

    async def version(self) -> str:
        result = await self.send_command("version")
        return result.response if result.success else "unknown"

    async def clear_board(self) -> bool:
        result = await self.send_command("clear_board")
        if result.success:
            # Reset score tracking since board is cleared
            self.previous_score = 0.0
            logger.debug("Reset previous_score to 0.0 (board cleared)")
        return result.success

    async def set_komi(self, komi: float) -> bool:
        result = await self.send_command("komi", str(komi))
        return result.success

    async def set_board_size(self, size: int) -> bool:
        result = await self.send_command("boardsize", str(size))
        if not result.success:
            logger.error(
                "Failed to set board size",
                size=size,
                response=result.response,
                message=result.message,
            )
        else:
            # Reset score tracking since board size changed (implies new game)
            self.previous_score = 0.0
            logger.debug(f"Reset previous_score to 0.0 (board size set to {size})")
        return result.success

    async def play(self, color: str, move: str) -> bool:
        result = await self.send_command("play", color, move)
        return result.success

    async def genmove(self, color: str) -> MoveResult:
        """Generate a move for the specified color.

        Note: Score delta calculation is now handled in process_user_move()
        to correctly measure the user's move quality, not KataGo's response.
        """
        try:
            result = await self.send_command("genmove", color, timeout=10.0)

            if not result.success:
                logger.warning(f"genmove failed: {result.message}")
                return MoveResult(move="", score_delta=0.0, raw_response=result.message)

            return MoveResult(move=result.response, score_delta=0.0, raw_response=result.message)

        except Exception as e:
            logger.error("Failed to generate move", error=str(e))
            return MoveResult(move="", score_delta=0.0, raw_response=str(e))

    async def kata_analyze(self) -> float:
        """Analyze current position and return score lead.

        Uses kata-analyze command to get score estimation.
        Falls back to simple evaluation if analysis fails.
        """
        try:
            # Send kata-analyze command with minimal parameters for fast response
            # Using very short analysis time (1 centisecond = 0.01 seconds) for maximum speed
            logger.debug("Sending kata-analyze command")
            result = await self.send_command("kata-analyze", "1", timeout=1.0)  # Shorter timeout
            logger.debug(
                f"kata-analyze result: success={result.success}, message_length={len(result.message) if result.message else 0}"
            )

            if result.success and result.message:
                logger.debug(
                    f"kata-analyze message length: {len(result.message) if result.message else 0}"
                )
                # Parse the response to extract scoreMean
                lines = result.message.split("\n")
                score_leads = []

                # Search through lines for scoreMean
                # Collect up to 10 scoreMean values for averaging
                lines_to_check = min(100, len(lines))
                for line in lines[:lines_to_check]:
                    line = line.strip()
                    # Skip response markers
                    if line.startswith(("=", "?")) or line == "":
                        continue

                    # Look for scoreMean in the analysis output
                    if "scoreMean" in line:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part == "scoreMean" and i + 1 < len(parts):
                                try:
                                    score_value = float(parts[i + 1])
                                    score_leads.append(score_value)
                                    logger.debug(
                                        f"Found scoreMean #{len(score_leads)}: {score_value}"
                                    )
                                    # Collect up to 10 values
                                    if len(score_leads) >= 10:
                                        break
                                except ValueError:
                                    logger.warning(
                                        f"Failed to parse scoreMean value from: {parts[i + 1]}"
                                    )
                                    continue
                        if len(score_leads) >= 10:
                            break

                if score_leads:
                    # Calculate average of collected scoreMean values
                    final_score = sum(score_leads) / len(score_leads)
                    logger.debug(
                        f"Returning average scoreMean from {len(score_leads)} values: {final_score}"
                    )
                    return final_score

            # Check if we got a response but no scoreMean
            if result.success:
                logger.warning(
                    f"kata-analyze succeeded but no scoreMean found in response (length: {len(result.message) if result.message else 0})"
                )
            else:
                logger.warning(f"kata-analyze failed: {result.message}")

        except Exception as e:
            logger.warning(f"kata-analyze failed with exception: {e}")

        # Fallback: Return 0.0 as neutral score when analysis fails
        # This maintains compatibility while avoiding timeouts
        return 0.0

    async def kata_analyze_normalized(self, color_to_move: str) -> float:
        """Get normalized score from kata-analyze.

        Returns score from Black's perspective:
        - Positive = Black is leading
        - Negative = White is leading

        Args:
            color_to_move: Which color is to move next ('B' or 'W')
        """
        raw_score = await self.kata_analyze()

        # kata-analyze returns score from perspective of color_to_move
        # If White is to move, negate to get Black's perspective
        if color_to_move == "W":
            normalized_score = -raw_score
        else:
            normalized_score = raw_score

        logger.debug(
            f"Normalized score: {raw_score} (from {color_to_move}'s perspective) -> {normalized_score} (Black's perspective)"
        )
        return normalized_score

    async def final_score(self) -> str | None:
        result = await self.send_command("final_score")
        return result.response if result.success else None

    async def final_status_list(self, status: str) -> list[str]:
        result = await self.send_command("final_status_list", status)
        if result.success and result.response:
            return result.response.split()
        return []

    async def get_handicap(self) -> int:
        result = await self.send_command("get_handicap")
        try:
            return int(result.response) if result.success else 0
        except ValueError:
            return 0

    async def is_terminated(self) -> bool:
        return self.process is None or self.process.returncode is not None

    async def showboard(self) -> str:
        """Get the current board state using GTP showboard command.
        Returns the raw showboard output string."""
        result = await self.send_command("showboard")
        # For showboard, the board data is in the message, not the response
        return result.message if result.success else ""

    async def fixed_handicap(self, num_stones: int) -> list[str]:
        """Place handicap stones at standard positions.
        Returns list of coordinates where stones were placed."""
        result = await self.send_command("fixed_handicap", str(num_stones))
        if result.success and result.response:
            # Response contains space-separated coordinates
            return result.response.split()
        return []

    async def place_free_handicap(self, num_stones: int) -> list[str]:
        """KataGo places handicap stones freely.
        Returns list of coordinates where stones were placed."""
        result = await self.send_command("place_free_handicap", str(num_stones))
        if result.success and result.response:
            return result.response.split()
        return []

    async def set_free_handicap(self, coordinates: list[str]) -> bool:
        """Manually place handicap stones at specific coordinates."""
        if not coordinates:
            return True
        args = ["set_free_handicap"] + coordinates
        result = await self.send_command(*args)
        return result.success

    def _parse_showboard_output(self, message: str, board_size: int = 19) -> list[list[str]]:
        """Parse the showboard GTP output into a 2D board array."""
        lines = message.strip().split("\n")
        board = []

        for line in lines:
            line = line.rstrip()
            if not line:
                continue
            if line[0].isdigit():
                parts = line.split(None, 1)
                if len(parts) == 2:
                    board_part = parts[1]
                else:
                    board_part = line

                row = []
                for char in board_part:
                    if char == "X":
                        row.append("B")
                    elif char == "O":
                        row.append("W")
                    elif char == ".":
                        row.append(".")

                while len(row) < board_size:
                    row.append(".")
                if row:
                    board.append(row)

        while len(board) < board_size:
            board.append(["."] * board_size)

        return board

    async def list_board(self) -> dict:
        """Get the current board state from KataGo using showboard command."""
        result = await self.send_command("showboard")
        if result.success and result.message:
            board = self._parse_showboard_output(result.message, 19)
            return {"board": board, "board_size": 19}
        return {"board": [], "board_size": 0}


async def create_gtp_client(
    katago_command: list[str] | None = None,
    board_size: int = 19,
    komi: float = 7.5,
    config: dict | None = None,
) -> GTPClient:
    client = GTPClient(katago_command, config)
    await client.start()

    success = await client.set_board_size(board_size)
    if not success:
        raise RuntimeError(f"Failed to set board size to {board_size}")

    await client.set_komi(komi)
    await client.clear_board()

    # Initialize previous_score by analyzing the starting position
    # This ensures we start with the actual score of an empty board
    # At the start, Black plays first
    client.previous_score = await client.kata_analyze_normalized("B")
    logger.debug(
        f"Initialized previous_score to {client.previous_score} (Black's perspective, starting position)"
    )

    return client
