import re
from dataclasses import dataclass, field
from enum import Enum


class Color(Enum):
    BLACK = "B"
    WHITE = "W"


@dataclass
class Move:
    color: Color
    coordinate: str
    pass_move: bool = False
    resignation: bool = False


@dataclass
class BoardState:
    size: int = 19
    moves: list[Move] = field(default_factory=list)
    handicap: int = 0
    komi: float = 6.5

    def last_move(self) -> Move | None:
        return self.moves[-1] if self.moves else None

    def to_gtp_history(self) -> str:
        history = []
        for move in self.moves:
            if move.pass_move:
                history.append(f"{move.color.value}[]")
            elif move.resignation:
                history.append(f"{move.color.value}resign")
            else:
                history.append(f"{move.color.value}[{move.coordinate}]")
        return " ".join(history)

    def current_color(self) -> Color:
        if self.size == 19 and self.handicap > 0:
            black_moves = 1 + self.handicap
        else:
            black_moves = len([m for m in self.moves if m.color == Color.BLACK])
        white_moves = len([m for m in self.moves if m.color == Color.WHITE])

        if black_moves == white_moves:
            return Color.BLACK
        return Color.WHITE

    def ai_color(self) -> Color:
        return Color.WHITE if self.current_color() == Color.BLACK else Color.BLACK

    def user_color(self) -> Color:
        return self.current_color()


def gtp_to_a19(gtp_coord: str, board_size: int = 19) -> str:
    if gtp_coord is None or gtp_coord == "" or gtp_coord == "pass":
        return "pass"

    if len(gtp_coord) < 2:
        return gtp_coord

    col_letter = gtp_coord[0].lower()
    row_part = gtp_coord[1:]

    if col_letter == "i":
        return ""

    col_map = {}
    col_letters = []
    for c in range(ord("a"), ord("z") + 1):
        if chr(c) != "i":
            col_letters.append(chr(c))
    for i, letter in enumerate(col_letters, 1):
        col_map[letter] = i

    try:
        if col_letter not in col_map:
            return gtp_coord
        row = int(row_part)
        if 1 <= row <= board_size:
            return f"{col_letter.upper()}{row}"
        return gtp_coord
    except (KeyError, ValueError):
        return gtp_coord


def a19_to_gtp(a19_coord: str, board_size: int = 19) -> str:
    if not a19_coord or a19_coord.lower() == "pass":
        return "pass"

    a19_coord = a19_coord.strip().upper()

    match = re.match(r"([A-HJ-Z])(\d+)", a19_coord)
    if not match:
        return "pass"

    col_letter = match.group(1)
    row_num = match.group(2)

    if col_letter == "I":
        return "pass"

    gtp_col = col_letter.lower()

    return f"{gtp_col}{row_num}"


def parse_move(user_input: str, board: BoardState) -> Move | None:
    user_input = user_input.strip().lower()

    if user_input in ["pass", "p", "0"]:
        return Move(color=board.current_color(), coordinate="", pass_move=True)

    if user_input in ["resign", "r", "quit", "q"]:
        return Move(color=board.current_color(), coordinate="", resignation=True)

    gtp_coord = a19_to_gtp(user_input, board.size)

    if gtp_coord == "pass":
        return None

    return Move(color=board.current_color(), coordinate=gtp_coord)


def format_move_for_display(gtp_coord: str, board_size: int = 19) -> str:
    return gtp_to_a19(gtp_coord, board_size).upper()


def format_score_delta(delta: float | None) -> str:
    if delta is None:
        return ""

    sign = "+" if delta > 0 else ""
    return f"{sign}{delta:.1f}"
