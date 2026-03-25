import requests
from datetime import datetime
from functools import lru_cache

BASE_URL = "https://statsapi.mlb.com/api/v1"


def search_player(name: str):
    """
    Searches MLB Stats API for a player by name.
    Returns a list of matching players with id, name, position, and team.
    """
    url = f"{BASE_URL}/people/search"
    params = {"names": name}

    response = requests.get(url, params=params)

    if response.status_code != 200:
        return []

    data = response.json()

    players = []

    if "people" not in data:
        return players

    for person in data["people"]:
        players.append({
            "id": person.get("id"),
            "name": person.get("fullName"),
            "position": person.get("primaryPosition", {}).get("abbreviation"),
            "team": person.get("currentTeam", {}).get("abbreviation"),
            "bat_side": person.get("batSide", {}).get("code"),
        })

    return players

def get_player_details(player_id: int):
    """
    Fetches detailed player info including current team.
    """
    url = f"{BASE_URL}/people/{player_id}"
    response = requests.get(url)

    if response.status_code != 200:
        return None

    data = response.json()

    if "people" not in data or not data["people"]:
        return None

    person = data["people"][0]

    return {
        "id": person.get("id"),
        "name": person.get("fullName"),
        "team": person.get("currentTeam", {}).get("abbreviation"),
        "bat_side": person.get("batSide", {}).get("code"),
        "pitch_hand": person.get("pitchHand", {}).get("code"),
    }


get_player_details = lru_cache(maxsize=512)(get_player_details)


def get_today_schedule():
    today = datetime.today().strftime("%Y-%m-%d")

    url = f"{BASE_URL}/schedule"
    params = {
        "sportId": 1,
        "date": today,
        "hydrate": "probablePitcher"
    }

    response = requests.get(url, params=params)

    if response.status_code != 200:
        return []

    data = response.json()

    if "dates" not in data or not data["dates"]:
        return []

    return data["dates"][0]["games"]


get_today_schedule = lru_cache(maxsize=1)(get_today_schedule)


def get_today_regular_season_games():
    """
    Returns today's regular season games only.
    """
    games = get_today_schedule()
    return [game for game in games if game.get("gameType") == "R"]


def get_live_game_feed(game_pk: int):
    """
    Fetches live feed payload for a game.
    """
    url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
    response = requests.get(url)

    if response.status_code != 200:
        return None

    return response.json()


get_live_game_feed = lru_cache(maxsize=64)(get_live_game_feed)


def _roster_contains_player(players_dict: dict, player_id: int):
    """
    MLB roster keys are usually formatted as 'ID<player_id>'.
    Fallback checks person.id for safety.
    """
    if not isinstance(players_dict, dict):
        return False

    key = f"ID{player_id}"
    if key in players_dict:
        return True

    for player_data in players_dict.values():
        person = player_data.get("person", {}) if isinstance(player_data, dict) else {}
        if person.get("id") == player_id:
            return True

    return False


def find_player_matchup_today(player_id: int):
    """
    Finds today's regular season game for the selected player.

    Returns a dict with matchup context, or None when no regular season games exist
    or the player is not in any active roster today.
    """
    games = get_today_regular_season_games()
    if not games:
        return None

    for game in games:
        game_pk = game.get("gamePk")
        if not game_pk:
            continue

        feed = get_live_game_feed(game_pk)
        if not feed:
            continue

        boxscore = (
            feed.get("liveData", {})
            .get("boxscore", {})
            .get("teams", {})
        )

        home_players = boxscore.get("home", {}).get("players", {})
        away_players = boxscore.get("away", {}).get("players", {})

        on_home = _roster_contains_player(home_players, player_id)
        on_away = _roster_contains_player(away_players, player_id)

        if not on_home and not on_away:
            continue

        player_side = "home" if on_home else "away"
        opponent_side = "away" if on_home else "home"
        opponent_info = game.get("teams", {}).get(opponent_side, {})
        probable_pitcher = opponent_info.get("probablePitcher")

        return {
            "game_pk": game_pk,
            "player_side": player_side,
            "opponent_side": opponent_side,
            "opponent_team": opponent_info.get("team", {}).get("abbreviation"),
            "opponent_probable_pitcher": probable_pitcher,
            "game": game,
        }

    return None


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_ops_from_splits(splits: list, left_tokens: list, right_tokens: list):
    left_ops = None
    right_ops = None

    for split in splits:
        split_info = split.get("split", {})
        stat = split.get("stat", {})
        ops = _safe_float(stat.get("ops"))
        if ops is None:
            continue

        split_text = " ".join(
            str(value).lower()
            for value in split_info.values()
            if isinstance(value, str)
        )

        if left_ops is None and any(token in split_text for token in left_tokens):
            left_ops = ops
        if right_ops is None and any(token in split_text for token in right_tokens):
            right_ops = ops

    return left_ops, right_ops


def get_hitter_ops_splits(player_id: int):
    """
    Returns hitter OPS splits as:
    {
      "vs_lhp": float|None,
      "vs_rhp": float|None
    }
    """
    url = f"{BASE_URL}/people/{player_id}/stats"
    params = {"stats": "splits", "group": "hitting"}
    response = requests.get(url, params=params)

    if response.status_code != 200:
        return {"vs_lhp": None, "vs_rhp": None}

    data = response.json()
    stats = data.get("stats", [])
    if not stats:
        return {"vs_lhp": None, "vs_rhp": None}

    splits = stats[0].get("splits", [])
    vs_lhp, vs_rhp = _extract_ops_from_splits(
        splits,
        left_tokens=["left", "lhp", "vs l"],
        right_tokens=["right", "rhp", "vs r"],
    )

    return {"vs_lhp": vs_lhp, "vs_rhp": vs_rhp}


get_hitter_ops_splits = lru_cache(maxsize=512)(get_hitter_ops_splits)


def get_pitcher_ops_allowed_splits(player_id: int):
    """
    Returns pitcher OPS allowed splits as:
    {
      "vs_lhb": float|None,
      "vs_rhb": float|None
    }
    """
    url = f"{BASE_URL}/people/{player_id}/stats"
    params = {"stats": "splits", "group": "pitching"}
    response = requests.get(url, params=params)

    if response.status_code != 200:
        return {"vs_lhb": None, "vs_rhb": None}

    data = response.json()
    stats = data.get("stats", [])
    if not stats:
        return {"vs_lhb": None, "vs_rhb": None}

    splits = stats[0].get("splits", [])
    vs_lhb, vs_rhb = _extract_ops_from_splits(
        splits,
        left_tokens=["left", "lhb", "vs l"],
        right_tokens=["right", "rhb", "vs r"],
    )

    return {"vs_lhb": vs_lhb, "vs_rhb": vs_rhb}


get_pitcher_ops_allowed_splits = lru_cache(maxsize=512)(get_pitcher_ops_allowed_splits)


def get_season_stats(player_id: int, season: int):
    """
    Returns season hitting stats for avg/obp/slg/ops, or None when unavailable.
    """
    url = f"{BASE_URL}/people/{player_id}/stats"
    params = {
        "stats": "season",
        "group": "hitting",
        "season": season,
    }
    response = requests.get(url, params=params)

    if response.status_code != 200:
        return None

    data = response.json()
    stats = data.get("stats", [])
    if not stats:
        return None

    splits = stats[0].get("splits", [])
    if not splits:
        return None

    stat = splits[0].get("stat", {})

    avg = _safe_float(stat.get("avg"))
    obp = _safe_float(stat.get("obp"))
    slg = _safe_float(stat.get("slg"))
    ops = _safe_float(stat.get("ops"))

    if avg is None or obp is None or slg is None or ops is None:
        return None

    return {
        "avg": avg,
        "obp": obp,
        "slg": slg,
        "ops": ops,
    }


get_season_stats = lru_cache(maxsize=1024)(get_season_stats)
