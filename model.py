from mlb_api import (
    find_player_matchup_today,
    get_hitter_ops_splits,
    get_pitcher_ops_allowed_splits,
    get_player_details,
)

LEAGUE_AVG_OPS = 0.720


def get_verdict(delta: float):
    if delta > 0.040:
        return "Strong Start"
    if delta > 0.010:
        return "Start"
    if delta > -0.020:
        return "Neutral"
    return "Bench"


def compute_expected_ops(hitter_ops_vs_hand: float, pitcher_ops_allowed_vs_side: float):
    return (hitter_ops_vs_hand * 0.65) + (pitcher_ops_allowed_vs_side * 0.35)


def _select_hitter_split(hitter_splits: dict, pitcher_hand: str):
    if pitcher_hand == "R":
        return hitter_splits.get("vs_rhp"), "vs_rhp"
    if pitcher_hand == "L":
        return hitter_splits.get("vs_lhp"), "vs_lhp"
    return None, None


def _effective_hitter_side_for_pitcher_split(hitter_bat_side: str, pitcher_hand: str):
    if hitter_bat_side == "S":
        if pitcher_hand == "R":
            return "L"
        if pitcher_hand == "L":
            return "R"
        return None

    if hitter_bat_side in {"R", "L"}:
        return hitter_bat_side

    return None


def _select_pitcher_split(pitcher_splits: dict, hitter_bat_side: str, pitcher_hand: str):
    effective_side = _effective_hitter_side_for_pitcher_split(hitter_bat_side, pitcher_hand)
    if effective_side == "R":
        return pitcher_splits.get("vs_rhb"), "vs_rhb"
    if effective_side == "L":
        return pitcher_splits.get("vs_lhb"), "vs_lhb"
    return None, None


def analyze_player_daily_matchup(player_id: int):
    """
    Full daily matchup analysis for one hitter.
    Returns a deterministic payload with either score details or an informative message.
    """
    matchup = find_player_matchup_today(player_id)
    if matchup is None:
        return {
            "ok": False,
            "message": "No regular season game found for this player today.",
        }

    probable_pitcher = matchup.get("opponent_probable_pitcher") or {}
    pitcher_id = probable_pitcher.get("id")
    pitcher_name = probable_pitcher.get("fullName")

    if not pitcher_id:
        return {
            "ok": False,
            "message": "Matchup found, but opponent probable pitcher is not available yet.",
            "matchup": matchup,
        }

    hitter_details = get_player_details(player_id) or {}
    pitcher_details = get_player_details(pitcher_id) or {}

    hitter_bat_side = hitter_details.get("bat_side")
    pitcher_hand = pitcher_details.get("pitch_hand")

    if pitcher_hand not in {"R", "L"}:
        return {
            "ok": False,
            "message": "Pitcher throwing hand is unavailable.",
            "matchup": matchup,
            "pitcher": {"id": pitcher_id, "name": pitcher_name},
        }

    hitter_splits = get_hitter_ops_splits(player_id)
    pitcher_splits = get_pitcher_ops_allowed_splits(pitcher_id)

    hitter_ops, hitter_split_used = _select_hitter_split(hitter_splits, pitcher_hand)
    pitcher_ops_allowed, pitcher_split_used = _select_pitcher_split(
        pitcher_splits,
        hitter_bat_side,
        pitcher_hand,
    )

    if hitter_ops is None:
        return {
            "ok": False,
            "message": "Missing hitter split data for this handedness matchup.",
            "matchup": matchup,
            "pitcher": {"id": pitcher_id, "name": pitcher_name, "throws": pitcher_hand},
            "hitter": {"id": player_id, "bats": hitter_bat_side},
        }

    if pitcher_ops_allowed is None:
        return {
            "ok": False,
            "message": "Missing pitcher split data for this handedness matchup.",
            "matchup": matchup,
            "pitcher": {"id": pitcher_id, "name": pitcher_name, "throws": pitcher_hand},
            "hitter": {"id": player_id, "bats": hitter_bat_side},
        }

    expected_ops = compute_expected_ops(hitter_ops, pitcher_ops_allowed)
    delta = expected_ops - LEAGUE_AVG_OPS

    return {
        "ok": True,
        "matchup": matchup,
        "hitter": {
            "id": player_id,
            "bats": hitter_bat_side,
            "split_used": hitter_split_used,
            "ops_used": hitter_ops,
        },
        "pitcher": {
            "id": pitcher_id,
            "name": pitcher_name,
            "throws": pitcher_hand,
            "split_used": pitcher_split_used,
            "ops_allowed_used": pitcher_ops_allowed,
        },
        "expected_ops": expected_ops,
        "league_avg_ops": LEAGUE_AVG_OPS,
        "delta": delta,
        "verdict": get_verdict(delta),
    }
