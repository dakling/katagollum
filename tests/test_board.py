import pytest
from src.game.board import gtp_to_a19, a19_to_gtp, parse_move, BoardState, Color, Move


class TestGtpToA19:
    def test_d4(self):
        assert gtp_to_a19("d4", 19) == "D4"

    def test_q4(self):
        assert gtp_to_a19("q4", 19) == "Q4"

    def test_t19(self):
        assert gtp_to_a19("t19", 19) == "T19"

    def test_pass(self):
        assert gtp_to_a19("pass", 19) == "pass"

    def test_empty(self):
        assert gtp_to_a19("", 19) == "pass"

    def test_a19_corner(self):
        assert gtp_to_a19("a19", 19) == "A19"

    def test_t1_corner(self):
        assert gtp_to_a19("t1", 19) == "T1"

    def test_row_10(self):
        assert gtp_to_a19("d10", 19) == "D10"

    def test_row_15(self):
        assert gtp_to_a19("d15", 19) == "D15"


class TestA19ToGtp:
    def test_d4(self):
        assert a19_to_gtp("D4", 19) == "d4"

    def test_q4(self):
        assert a19_to_gtp("Q4", 19) == "q4"

    def test_t19(self):
        assert a19_to_gtp("T19", 19) == "t19"

    def test_pass(self):
        assert a19_to_gtp("pass", 19) == "pass"

    def test_uppercase(self):
        assert a19_to_gtp("d4", 19) == "d4"

    def test_a19(self):
        assert a19_to_gtp("A19", 19) == "a19"

    def test_t1(self):
        assert a19_to_gtp("T1", 19) == "t1"

    def test_row_10(self):
        assert a19_to_gtp("D10", 19) == "d10"

    def test_row_15(self):
        assert a19_to_gtp("D15", 19) == "d15"


class TestParseMove:
    def test_parse_d4(self):
        board = BoardState()
        move = parse_move("D4", board)
        assert move is not None
        assert move.color == Color.BLACK
        assert move.coordinate == "d4"

    def test_parse_pass(self):
        board = BoardState()
        move = parse_move("pass", board)
        assert move is not None
        assert move.pass_move is True

    def test_parse_resign(self):
        board = BoardState()
        move = parse_move("resign", board)
        assert move is not None
        assert move.resignation is True


class TestBoardState:
    def test_initial_state(self):
        board = BoardState()
        assert board.size == 19
        assert board.moves == []
        assert board.current_color() == Color.BLACK

    def test_ai_color(self):
        board = BoardState()
        assert board.ai_color() == Color.WHITE

    def test_user_color(self):
        board = BoardState()
        assert board.user_color() == Color.BLACK

    def test_to_gtp_history_empty(self):
        board = BoardState()
        assert board.to_gtp_history() == ""

    def test_to_gtp_history_with_moves(self):
        board = BoardState()
        board.moves = [
            Move(color=Color.BLACK, coordinate="d4"),
            Move(color=Color.WHITE, coordinate="q4"),
        ]
        assert board.to_gtp_history() == "B[d4] W[q4]"


class TestRoundTrip:
    @pytest.mark.parametrize("gtp_coord", ["d4", "q4", "t19", "a19", "t1", "d10", "d15"])
    def test_gtp_to_a19_to_gtp(self, gtp_coord):
        a19 = gtp_to_a19(gtp_coord, 19)
        gtp_back = a19_to_gtp(a19, 19)
        assert gtp_back == gtp_coord, f"Failed for {gtp_coord}: {a19} -> {gtp_back}"

    @pytest.mark.parametrize("a19_coord", ["D4", "Q4", "T19", "A19", "T1", "D10", "D15"])
    def test_a19_to_gtp_to_a19(self, a19_coord):
        gtp = a19_to_gtp(a19_coord, 19)
        a19_back = gtp_to_a19(gtp, 19)
        assert a19_back.upper() == a19_coord.upper(), f"Failed for {a19_coord}: {gtp} -> {a19_back}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
