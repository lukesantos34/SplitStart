import streamlit as st
from concurrent.futures import ThreadPoolExecutor, as_completed

from mlb_api import get_season_stats, search_player
from model import analyze_player_daily_matchup

st.set_page_config(page_title="Fantasy Daily Split Analyzer")

st.title("Fantasy Daily Split Analyzer")

if "selected_hitters" not in st.session_state:
    st.session_state.selected_hitters = []

player_name = st.text_input("Search player to add")

if player_name:
    results = search_player(player_name)
else:
    results = []

if player_name and not results:
    st.warning("No players found.")

if results:
    selected = st.selectbox(
        "Select player to add",
        results,
        format_func=lambda x: f"{x['name']} - {x['position']} - {x['team']}"
    )

    if st.button("Add Hitter"):
        hitter_ids = {hitter["id"] for hitter in st.session_state.selected_hitters}

        if selected["id"] in hitter_ids:
            st.info("Player already added.")
        elif len(st.session_state.selected_hitters) >= 5:
            st.warning("You can select up to 5 hitters.")
        else:
            st.session_state.selected_hitters.append(selected)
            st.success(f"Added {selected['name']}")

if st.session_state.selected_hitters:
    st.subheader("Selected Hitters")
    st.write(
        ", ".join(
            f"{hitter['name']} ({hitter.get('team', 'N/A')})"
            for hitter in st.session_state.selected_hitters
        )
    )

    if st.button("Clear Hitters"):
        st.session_state.selected_hitters = []
        st.rerun()


def _analyze_hitter(hitter: dict):
    player_id = hitter["id"]
    return {
        "player": hitter,
        "matchup": analyze_player_daily_matchup(player_id),
        "season_2025": get_season_stats(player_id, 2025),
        "season_2026": get_season_stats(player_id, 2026),
    }


if st.button("Analyze Selected Hitters"):
    hitter_count = len(st.session_state.selected_hitters)

    if hitter_count < 3:
        st.warning("Please add at least 3 hitters.")
    elif hitter_count > 5:
        st.warning("Please keep selection to 5 hitters max.")
    else:
        results = []
        max_workers = min(5, hitter_count)

        with st.spinner("Analyzing hitters..."):
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(_analyze_hitter, hitter)
                    for hitter in st.session_state.selected_hitters
                ]

                for future in as_completed(futures):
                    try:
                        results.append(future.result())
                    except Exception as exc:
                        results.append(
                            {
                                "player": {"name": "Unknown", "team": "N/A"},
                                "matchup": {
                                    "ok": False,
                                    "message": f"Unexpected error during analysis: {exc}",
                                },
                                "season_2025": None,
                                "season_2026": None,
                            }
                        )

        result_by_id = {item["player"].get("id"): item for item in results}
        ordered_results = [
            result_by_id.get(hitter["id"])
            for hitter in st.session_state.selected_hitters
            if result_by_id.get(hitter["id"]) is not None
        ]

        st.subheader("Batch Analysis")

        for item in ordered_results:
            player = item["player"]
            analysis = item["matchup"]
            season_2025 = item["season_2025"]
            season_2026 = item["season_2026"]

            with st.container(border=True):
                st.markdown(f"### {player['name']} ({player.get('team', 'N/A')})")

                left_col, right_col = st.columns(2)

                with left_col:
                    st.markdown("**Matchup**")

                    if not analysis.get("ok"):
                        st.info(analysis.get("message", "No matchup analysis available."))
                    else:
                        matchup = analysis.get("matchup", {})
                        pitcher = analysis.get("pitcher", {})
                        hitter = analysis.get("hitter", {})

                        st.write(f"Opponent: {matchup.get('opponent_team', 'N/A')}")
                        st.write(
                            f"Probable Pitcher: {pitcher.get('name', 'N/A')} ({pitcher.get('throws', 'N/A')})"
                        )
                        st.write(f"Expected OPS: {analysis['expected_ops']:.3f}")
                        st.write(f"Delta: {analysis['delta']:+.3f}")
                        st.write(f"Verdict: {analysis['verdict']}")
                        st.caption(
                            "Split details: "
                            f"hitter {hitter.get('split_used')}={hitter.get('ops_used'):.3f}, "
                            f"pitcher {pitcher.get('split_used')}={pitcher.get('ops_allowed_used'):.3f}"
                        )

                with right_col:
                    st.markdown("**Season Stats**")
                    year_2025, year_2026 = st.columns(2)

                    with year_2025:
                        st.markdown("2025")
                        if season_2025 is None:
                            st.write("No Data")
                        else:
                            st.write(f"AVG: {season_2025['avg']:.3f}")
                            st.write(f"OBP: {season_2025['obp']:.3f}")
                            st.write(f"SLG: {season_2025['slg']:.3f}")
                            st.write(f"OPS: {season_2025['ops']:.3f}")

                    with year_2026:
                        st.markdown("2026")
                        if season_2026 is None:
                            st.write("No Data")
                        else:
                            st.write(f"AVG: {season_2026['avg']:.3f}")
                            st.write(f"OBP: {season_2026['obp']:.3f}")
                            st.write(f"SLG: {season_2026['slg']:.3f}")
                            st.write(f"OPS: {season_2026['ops']:.3f}")