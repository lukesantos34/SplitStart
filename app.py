import streamlit as st
from mlb_api import search_player
from model import analyze_player_daily_matchup

st.set_page_config(page_title="Fantasy Daily Split Analyzer")

st.title("Fantasy Daily Split Analyzer")

player_name = st.text_input("Enter player name")

if player_name:
    results = search_player(player_name)

    if not results:
        st.warning("No players found.")
    else:
        selected = st.selectbox(
            "Select player",
            results,
            format_func=lambda x: f"{x['name']} - {x['position']} - {x['team']}"
        )

        if st.button("Analyze Matchup"):
            analysis = analyze_player_daily_matchup(selected["id"])

            with st.container(border=True):
                st.subheader("Analyze Matchup")
                st.write(f"Player: {selected['name']}")

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

                    st.metric("Expected OPS", f"{analysis['expected_ops']:.3f}")
                    st.write(f"League Avg OPS: {analysis['league_avg_ops']:.3f}")
                    st.write(f"Delta: {analysis['delta']:+.3f}")
                    st.write(f"Verdict: {analysis['verdict']}")

                    st.caption(
                        "Split details: "
                        f"hitter {hitter.get('split_used')}={hitter.get('ops_used'):.3f}, "
                        f"pitcher {pitcher.get('split_used')}={pitcher.get('ops_allowed_used'):.3f}"
                    )