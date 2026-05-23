import re
import unicodedata

import chess
import chess.engine


DEFAULT_ANALYSIS_LIMIT = chess.engine.Limit(time=0.12)
QUICK_ANALYSIS_LIMIT = chess.engine.Limit(time=0.05)
PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}
SAN_CANDIDATE_RE = re.compile(
    r"\b(?:O-O-O|O-O|0-0-0|0-0|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?)\b"
)
UCI_CANDIDATE_RE = re.compile(r"\b[a-h][1-8][a-h][1-8][qrbn]?\b")
NATURAL_MOVE_RE = re.compile(
    r"\b(?P<piece>caballo|cavalo|knight|horse|dama|reina|queen|torre|rook|bispo|alfil|bishop|rey|rei|king|pe[oóã]n|peão|pawn)\s+"
    r"(?:a|en|em|para|to)?\s*(?P<target>[a-h][1-8])\b",
    re.IGNORECASE,
)
NATURAL_PIECES = {
    "caballo": chess.KNIGHT,
    "cavalo": chess.KNIGHT,
    "knight": chess.KNIGHT,
    "horse": chess.KNIGHT,
    "dama": chess.QUEEN,
    "reina": chess.QUEEN,
    "queen": chess.QUEEN,
    "torre": chess.ROOK,
    "rook": chess.ROOK,
    "bispo": chess.BISHOP,
    "alfil": chess.BISHOP,
    "bishop": chess.BISHOP,
    "rey": chess.KING,
    "rei": chess.KING,
    "king": chess.KING,
    "peon": chess.PAWN,
    "peon": chess.PAWN,
    "peao": chess.PAWN,
    "pawn": chess.PAWN,
}


def score_to_cp(score):
    if score.is_mate():
        mate = score.mate()
        return 100000 if mate and mate > 0 else -100000

    return score.score(mate_score=100000) or 0


def color_name(color):
    return "white" if color == chess.WHITE else "black"


def piece_name(piece_type):
    return {
        chess.PAWN: "pawn",
        chess.KNIGHT: "knight",
        chess.BISHOP: "bishop",
        chess.ROOK: "rook",
        chess.QUEEN: "queen",
        chess.KING: "king",
    }[piece_type]


def normalize_piece_text(text):
    return "".join(
        char for char in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(char)
    )


def score_for_player(score_cp_white, player_color):
    return score_cp_white if player_color == "white" else -score_cp_white


def describe_score(score_cp):
    if abs(score_cp) >= 90000:
        return "mate sequence"
    if score_cp > 180:
        return "clear advantage"
    if score_cp > 60:
        return "small advantage"
    if score_cp < -180:
        return "clear disadvantage"
    if score_cp < -60:
        return "small disadvantage"
    return "roughly equal"


def san_or_uci(board, move):
    try:
        return board.san(move)
    except (AssertionError, ValueError):
        return move.uci()


def pv_to_san(board, pv, max_moves=5):
    line_board = board.copy()
    san_line = []

    for move in pv[:max_moves]:
        if move not in line_board.legal_moves:
            break

        san_line.append(line_board.san(move))
        line_board.push(move)

    return san_line


def engine_multipv(engine, board, limit=DEFAULT_ANALYSIS_LIMIT, multipv=3):
    analyses = engine.analyse(board, limit, multipv=multipv)
    if isinstance(analyses, dict):
        analyses = [analyses]

    lines = []
    for item in analyses:
        pv = item.get("pv") or []
        if not pv:
            continue

        score_cp_white = score_to_cp(item["score"].white())
        lines.append({
            "move_san": san_or_uci(board, pv[0]),
            "move_uci": pv[0].uci(),
            "score_cp_white": score_cp_white,
            "pv_san": pv_to_san(board, pv),
        })

    return lines


def material_summary(board):
    white = 0
    black = 0
    pieces = {"white": {}, "black": {}}

    for piece in board.piece_map().values():
        value = PIECE_VALUES[piece.piece_type]
        color = color_name(piece.color)
        pieces[color][piece_name(piece.piece_type)] = pieces[color].get(piece_name(piece.piece_type), 0) + 1

        if piece.color == chess.WHITE:
            white += value
        else:
            black += value

    return {
        "white": white,
        "black": black,
        "balance_white_minus_black": white - black,
        "pieces": pieces,
    }


def immediate_threats(board):
    checks = []
    captures = []

    for move in board.legal_moves:
        if board.gives_check(move):
            checks.append(san_or_uci(board, move))
            continue

        if board.is_capture(move):
            captured = board.piece_at(move.to_square)
            if captured is None and board.piece_at(move.from_square).piece_type == chess.PAWN:
                captured = board.piece_at(chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square)))

            captures.append({
                "move": san_or_uci(board, move),
                "captured": piece_name(captured.piece_type) if captured else "unknown",
            })

    return {
        "side_to_move": color_name(board.turn),
        "checks": checks[:5],
        "captures": captures[:6],
    }


def king_state(board):
    states = {}

    for color in (chess.WHITE, chess.BLACK):
        king_square = board.king(color)
        if king_square is None:
            states[color_name(color)] = {"in_check": False, "square": None, "attackers": []}
            continue

        attackers = [
            chess.square_name(square)
            for square in board.attackers(not color, king_square)
        ]
        states[color_name(color)] = {
            "in_check": board.is_check() and board.turn == color,
            "square": chess.square_name(king_square),
            "attackers": attackers,
        }

    return states


def parse_proposed_move(board, question):
    natural_match = NATURAL_MOVE_RE.search(question)
    if natural_match:
        piece_text = normalize_piece_text(natural_match.group("piece"))
        piece_type = NATURAL_PIECES.get(piece_text)
        target = natural_match.group("target")
        target_square = chess.parse_square(target)
        legal_matches = []

        for move in board.legal_moves:
            piece = board.piece_at(move.from_square)

            if piece and piece.piece_type == piece_type and move.to_square == target_square:
                legal_matches.append(move)

        if len(legal_matches) == 1:
            return {
                "raw": natural_match.group(0),
                "move": legal_matches[0],
                "legal": True,
            }

        return {
            "raw": natural_match.group(0),
            "move": None,
            "legal": False,
            "piece_type": piece_name(piece_type) if piece_type else None,
            "target": target,
            "reason": "No legal move by that piece type reaches the target square.",
        }

    candidates = []

    for match in SAN_CANDIDATE_RE.finditer(question):
        candidates.append(match.group(0))

    for match in UCI_CANDIDATE_RE.finditer(question):
        candidates.append(match.group(0))

    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)

        normalized = candidate.replace("0-0", "O-O")
        try:
            move = board.parse_san(normalized)
            return {"raw": candidate, "move": move, "legal": True}
        except ValueError:
            pass

        try:
            move = chess.Move.from_uci(candidate.lower())
        except ValueError:
            continue

        if move in board.legal_moves:
            return {"raw": candidate, "move": move, "legal": True}

        return {"raw": candidate, "move": move, "legal": False}

    return None


def analyze_proposed_move(engine, board, proposed, before_score_cp_white):
    if not proposed:
        return None

    move = proposed["move"]
    if not proposed["legal"]:
        return {
            "raw": proposed["raw"],
            "legal": False,
            "piece_type": proposed.get("piece_type"),
            "target": proposed.get("target"),
            "reason": proposed.get("reason") or "The proposed move is not legal in the current position.",
        }

    moving_color = board.turn
    move_san = board.san(move)
    board_after = board.copy()
    board_after.push(move)
    after = engine.analyse(board_after, QUICK_ANALYSIS_LIMIT)
    after_score_cp_white = score_to_cp(after["score"].white())
    response_move = (after.get("pv") or [None])[0]
    response_san = san_or_uci(board_after, response_move) if response_move else None
    change_for_mover = (
        after_score_cp_white - before_score_cp_white
        if moving_color == chess.WHITE
        else before_score_cp_white - after_score_cp_white
    )

    return {
        "raw": proposed["raw"],
        "legal": True,
        "move_san": move_san,
        "move_uci": move.uci(),
        "before_score_cp_white": before_score_cp_white,
        "after_score_cp_white": after_score_cp_white,
        "change_for_mover_cp": change_for_mover,
        "engine_reply_san": response_san,
        "resulting_fen": board_after.fen(),
    }


def build_trainer_engine_context(engine, board, san_moves, question, player_color, language="pt", opening_name=""):
    lines = engine_multipv(engine, board, DEFAULT_ANALYSIS_LIMIT, multipv=3)
    best_line = lines[0] if lines else None
    score_cp_white = best_line["score_cp_white"] if best_line else 0
    proposed = parse_proposed_move(board, question)

    return {
        "context_type": "trainer_chat_position",
        "language": language,
        "fen": board.fen(),
        "turn": color_name(board.turn),
        "player_color": player_color,
        "player_to_move": color_name(board.turn) == player_color,
        "move_count": len(san_moves),
        "recent_moves_san": san_moves[-16:],
        "opening": opening_name,
        "engine": {
            "score_cp_white": score_cp_white,
            "score_cp_for_player": score_for_player(score_cp_white, player_color),
            "evaluation_for_player": describe_score(score_for_player(score_cp_white, player_color)),
            "best_move_san": best_line["move_san"] if best_line else None,
            "best_move_uci": best_line["move_uci"] if best_line else None,
            "principal_variation_san": best_line["pv_san"] if best_line else [],
            "candidate_lines": lines,
        },
        "proposed_move": analyze_proposed_move(engine, board, proposed, score_cp_white),
        "threats": immediate_threats(board),
        "material": material_summary(board),
        "king_state": king_state(board),
        "legal_moves_san": [san_or_uci(board, move) for move in list(board.legal_moves)[:40]],
    }


def build_pgn_analysis_context(move_analysis, pgn_text="", selected_move_number=None, max_items=24):
    items = move_analysis[-max_items:]

    if selected_move_number is not None:
        selected = [
            item for item in move_analysis
            if item.get("move_number") == selected_move_number
        ]
        items = selected or items

    return {
        "context_type": "pgn_analysis",
        "pgn_excerpt": pgn_text[:2000],
        "selected_move_number": selected_move_number,
        "move_count": len(move_analysis),
        "engine_move_analysis": items,
    }
