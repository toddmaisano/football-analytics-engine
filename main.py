from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import duckdb

app = FastAPI()

DB_PATH = "football_warehouse.db"

def run_query(query: str, params=None):
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute(query, params).df() if params else con.execute(query).df()
    con.close()
    return df

def format_season(code: str) -> str:
    code_str = str(code).strip()
    if len(code_str) == 4:
        century = "19" if int(code_str[:2]) > 50 else "20"
        return f"{century}{code_str[:2]}/{code_str[2:]}"
    elif len(code_str) == 8:
        return f"{code_str[:4]}/{code_str[6:]}"
    elif len(code_str) == 6:
        return f"{code_str[:4]}/{code_str[4:]}"
    return code_str

@app.get("/api/seasons")
def get_seasons():
    df = run_query("SELECT DISTINCT season_code FROM main.fct_matches WHERE season_code IS NOT NULL ORDER BY season_code DESC")
    if df.empty or 'season_code' not in df.columns:
        return [{"code": "2425", "label": "2024/25"}]
    return [{"code": str(s), "label": format_season(str(s))} for s in df['season_code'].tolist()]

@app.get("/api/teams")
def get_teams(season: str = None):
    query = "SELECT DISTINCT team_name FROM main.fct_team_match_performance WHERE CAST(season_code AS VARCHAR) = ? ORDER BY team_name ASC" if season and season != "ALL" else "SELECT DISTINCT team_name FROM main.fct_team_match_performance ORDER BY team_name ASC"
    df = run_query(query, [season] if season and season != "ALL" else None)
    return df['team_name'].tolist() if not df.empty else []

@app.get("/api/team-seasons")
def get_team_seasons(team_name: str):
    if not team_name or team_name == "ALL":
        return []
    df = run_query("SELECT DISTINCT season_code FROM main.fct_team_match_performance WHERE team_name ILIKE ? ORDER BY season_code DESC", [f"%{team_name}%"])
    return [str(s) for s in df['season_code'].tolist()] if not df.empty else []

@app.get("/api/dashboard-master")
def get_dashboard_master(
    season: str = "ALL", 
    team: str = "ALL", 
    h2h_a: str = "Arsenal", 
    h2h_b: str = "Chelsea",
    momentum_seasons: str = "ALL",
    elo_season: str = "ALL"
):
    # 1. H2H Data
    h2h_matches_df = run_query("""
        SELECT match_date, season_code, home_team, away_team, home_goals, away_goals,
               ROUND(COALESCE(home_xg, 0), 2) AS home_xg, ROUND(COALESCE(away_xg, 0), 2) AS away_xg,
               CASE WHEN home_team ILIKE ? THEN home_goals - away_goals ELSE away_goals - home_goals END AS team_a_goal_diff,
               CASE WHEN home_team ILIKE ? THEN ROUND(COALESCE(home_xg - away_xg, 0), 2) ELSE ROUND(COALESCE(away_xg - home_xg, 0), 2) END AS team_a_xg_diff
        FROM main.fct_matches
        WHERE (home_team ILIKE ? AND away_team ILIKE ?) OR (home_team ILIKE ? AND away_team ILIKE ?)
        ORDER BY match_date ASC
    """, [f"%{h2h_a}%", f"%{h2h_a}%", f"%{h2h_a}%", f"%{h2h_b}%", f"%{h2h_b}%", f"%{h2h_a}%"]).fillna(0)
    
    h2h_traj_df = run_query("""
        SELECT season_code, team_name, ROUND(COALESCE(AVG(xg_for), 0), 2) AS avg_xg
        FROM main.fct_team_match_performance
        WHERE team_name ILIKE ? OR team_name ILIKE ?
        GROUP BY season_code, team_name
        ORDER BY CAST(season_code AS INT) ASC
    """, [f"%{h2h_a}%", f"%{h2h_b}%"]).fillna(0)

    h2h_style_df = run_query("""
        SELECT team_name, ROUND(COALESCE(AVG(possession_pct), 50), 1) AS possession,
               ROUND(COALESCE(AVG(shots_for), 0), 1) AS shots,
               ROUND(COALESCE(AVG(shots_on_target_for), 0), 1) AS shots_on_target,
               ROUND(COALESCE(AVG(xg_per_shot), 0), 3) AS xg_per_shot
        FROM main.fct_team_match_performance
        WHERE (team_name ILIKE ? OR team_name ILIKE ?) AND (opponent_name ILIKE ? OR opponent_name ILIKE ?)
        GROUP BY team_name
    """, [f"%{h2h_a}%", f"%{h2h_b}%", f"%{h2h_a}%", f"%{h2h_b}%"]).fillna(0)

    h2h_disc_df = run_query("""
        SELECT match_date, season_code, team_name, opponent_name, venue, result,
               fouls_committed, yellow_cards, red_cards,
               ROUND(COALESCE(xg_for - xg_against, 0), 2) AS xg_diff
        FROM main.fct_team_match_performance
        WHERE team_name ILIKE ? AND opponent_name ILIKE ?
        ORDER BY match_date ASC
    """, [f"%{h2h_a}%", f"%{h2h_b}%"]).fillna(0)

    # 2. Filtered Single-Season / Global Charts Data
    filters, params = [], []
    if team != "ALL":
        filters.append("team_name ILIKE ?")
        params.append(f"%{team}%")
    if season != "ALL":
        filters.append("CAST(season_code AS VARCHAR) = ?")
        params.append(season)
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    quadrant_df = run_query(f"""
        SELECT team_name, season_code,
               ROUND(COALESCE(AVG(xg_for - xg_against), 0), 2) AS avg_xg_diff,
               ROUND(COALESCE(AVG(goals_for - goals_against), 0), 2) AS avg_goal_diff
        FROM main.fct_team_match_performance {where_clause}
        GROUP BY team_name, season_code ORDER BY season_code ASC, avg_xg_diff DESC
    """, params if params else None).fillna(0)

    # 3. Elo Query with independent season filtering
    elo_filters, elo_params = [], []
    if team != "ALL":
        elo_filters.append("(home_team ILIKE ? OR away_team ILIKE ?)")
        elo_params.extend([f"%{team}%", f"%{team}%"])
    if elo_season != "ALL":
        elo_filters.append("CAST(season_code AS VARCHAR) = ?")
        elo_params.append(elo_season)
    elif season != "ALL":
        elo_filters.append("CAST(season_code AS VARCHAR) = ?")
        elo_params.append(season)
    
    elo_where = f"WHERE {' AND '.join(elo_filters)}" if elo_filters else ""

    elo_df = run_query(f"""
        SELECT season_code, match_date, home_team, away_team,
               ROUND(COALESCE(elo_diff, 0), 1) AS elo_diff,
               CASE WHEN full_time_result = 'H' THEN 1.0 WHEN full_time_result = 'D' THEN 0.5 ELSE 0.0 END AS match_outcome_val
        FROM main.fct_matches {elo_where} ORDER BY match_date ASC
    """, elo_params if elo_params else None).fillna(0)

    funnel_df = run_query(f"""
        SELECT team_name, season_code,
               ROUND(COALESCE(SUM(shots_for), 0), 0) AS total_shots,
               ROUND(COALESCE(SUM(shots_on_target_for), 0), 0) AS shots_on_target,
               ROUND(COALESCE(SUM(xg_for), 0), 1) AS total_xg,
               ROUND(COALESCE(SUM(goals_for), 0), 0) AS total_goals
        FROM main.fct_team_match_performance {where_clause}
        GROUP BY team_name, season_code ORDER BY season_code ASC, total_xg DESC
    """, params if params else None).fillna(0)

    possession_df = run_query(f"""
        SELECT team_name, season_code,
               ROUND(COALESCE(AVG(possession_pct), 50), 1) AS avg_possession,
               ROUND(COALESCE(AVG(touches_in_opp_box / NULLIF(final_third_entries, 0)), 0), 3) AS penetration_efficiency
        FROM main.fct_team_match_performance {where_clause}
        GROUP BY team_name, season_code ORDER BY season_code ASC, avg_possession DESC
    """, params if params else None).fillna(0)

    halftime_df = run_query(f"""
        SELECT team_name, season_code,
               COUNT(CASE WHEN ht_goals_for < ht_goals_against AND goals_for > goals_against THEN 1 END) AS halftime_comebacks,
               COUNT(CASE WHEN ht_goals_for > ht_goals_against AND goals_for < goals_against THEN 1 END) AS leads_blown
        FROM main.fct_team_match_performance {where_clause}
        GROUP BY team_name, season_code ORDER BY season_code ASC, halftime_comebacks DESC
    """, params if params else None).fillna(0)

    chaos_df = run_query(f"""
        SELECT team_name, season_code,
               ROUND(COALESCE(AVG(COALESCE(fouls_committed, 0) + COALESCE(yellow_cards, 0) * 2 + COALESCE(red_cards, 0) * 5), 0), 1) AS chaos_index,
               ROUND(COALESCE(AVG(final_third_entries), 0), 1) AS defensive_workload
        FROM main.fct_team_match_performance {where_clause}
        GROUP BY team_name, season_code ORDER BY season_code ASC, chaos_index DESC
    """, params if params else None).fillna(0)

    # Momentum Query
    mom_filters = []
    mom_params = []
    if momentum_seasons != "ALL":
        s_list = [s.strip() for s in momentum_seasons.split(",") if s.strip()]
        if s_list:
            mom_filters.append(f"CAST(season_code AS VARCHAR) IN ({','.join(['?']*len(s_list))})")
            mom_params.extend(s_list)
    elif season != "ALL":
        mom_filters.append("CAST(season_code AS VARCHAR) = ?")
        mom_params.append(season)
    
    if team != "ALL":
        mom_filters.append("team_name ILIKE ?")
        mom_params.append(f"%{team}%")
    else:
        mom_filters.append("CAST(season_code AS VARCHAR) = (SELECT CAST(MAX(season_code) AS VARCHAR) FROM main.fct_team_match_performance)")
        mom_filters.append("team_name IN ('Arsenal', 'Manchester City', 'Liverpool', 'Chelsea', 'Tottenham Hotspur', 'Manchester United', 'Aston Villa', 'Newcastle United')")

    mom_where = f"WHERE {' AND '.join(mom_filters)}" if mom_filters else ""

    momentum_df = run_query(f"""
        WITH ranked_matches AS (
            SELECT team_name, season_code, match_date,
                   COALESCE(xg_for, goals_for, 1.0) AS metric_val,
                   ROW_NUMBER() OVER (PARTITION BY team_name, season_code ORDER BY match_date ASC) as game_index
            FROM main.fct_team_match_performance {mom_where}
        )
        SELECT team_name, season_code, game_index AS normalized_date,
               ROUND(AVG(metric_val) OVER (PARTITION BY team_name, season_code ORDER BY game_index ROWS BETWEEN 4 PRECEDING AND CURRENT ROW), 2) AS rolling_value
        FROM ranked_matches
        ORDER BY season_code ASC, game_index ASC
    """, mom_params if mom_params else None).fillna(0)

    for df_item in [h2h_matches_df, h2h_traj_df, h2h_disc_df, quadrant_df, elo_df, funnel_df, possession_df, halftime_df, chaos_df, momentum_df]:
        if 'season_code' in df_item.columns:
            df_item['season_label'] = df_item['season_code'].apply(lambda x: format_season(str(x)))

    return {
        "h2h": {
            "matches": h2h_matches_df.to_dict(orient="records"),
            "trajectory": h2h_traj_df.to_dict(orient="records"),
            "style": h2h_style_df.to_dict(orient="records"),
            "discipline": h2h_disc_df.to_dict(orient="records")
        },
        "quadrant": quadrant_df.to_dict(orient="records"),
        "elo": elo_df.to_dict(orient="records"),
        "funnel": funnel_df.to_dict(orient="records"),
        "possession": possession_df.to_dict(orient="records"),
        "halftime": halftime_df.to_dict(orient="records"),
        "chaos": chaos_df.to_dict(orient="records"),
        "momentum": momentum_df.to_dict(orient="records")
    }

@app.get("/api/team-details")
def get_team_details(team_name: str, season: str):
    df = run_query("""
        SELECT match_date, opponent_name, venue, goals_for, goals_against,
               ROUND(COALESCE(xg_for, 0), 2) AS xg_for, ROUND(COALESCE(xg_against, 0), 2) AS xg_against, result
        FROM main.fct_team_match_performance WHERE team_name ILIKE ? AND CAST(season_code AS VARCHAR) = ? ORDER BY match_date DESC
    """, [f"%{team_name}%", season]).fillna(0)
    return df.to_dict(orient="records")

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!DOCTYPE html>
    <html lang="en" class="dark">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Premier League Analytics Engine</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <script>
            tailwind.config = {
                darkMode: 'class',
                theme: {
                    extend: {
                        colors: {
                            slate: { 850: '#151c2c', 900: '#0f172a', 950: '#090d16' }
                        }
                    }
                }
            }
        </script>
        <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
        <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
        <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
        <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    </head>
    <body class="bg-slate-950 text-slate-100 font-sans antialiased selection:bg-sky-500 selection:text-white">
        <div id="root"></div>

        <script type="text/babel">
            const formatSeasonLabel = (code, seasonsList) => {
                if (!code || code === "ALL") return "All Seasons";
                const found = seasonsList.find(s => s.code === code);
                return found ? found.label : code;
            };

            const InfoAccordion = ({ title, whatIsIt, goodVsBad }) => {
                const [isOpen, setIsOpen] = React.useState(false);
                return (
                    <div className="mt-3 border border-slate-800/80 bg-slate-950/40 rounded-xl overflow-hidden shadow-inner">
                        <button 
                            onClick={() => setIsOpen(!isOpen)}
                            className="w-full px-3.5 py-2.5 text-left flex items-center justify-between text-xs font-semibold text-sky-400 hover:bg-slate-800/40 transition-colors"
                        >
                            <span className="flex items-center gap-1.5"><span className="text-sm">💡</span> What am I looking at?</span>
                            <span className="text-slate-500 font-mono">{isOpen ? "▲ Hide" : "▼ Explain"}</span>
                        </button>
                        {isOpen && (
                            <div className="p-3.5 border-t border-slate-800/60 text-xs space-y-2.5 bg-slate-900/60">
                                <div>
                                    <strong className="text-slate-200 block mb-0.5 uppercase tracking-wider text-[10px]">What it measures:</strong>
                                    <p className="text-slate-400 leading-relaxed">{whatIsIt}</p>
                                </div>
                                {goodVsBad && (
                                    <div>
                                        <strong className="text-slate-200 block mb-0.5 uppercase tracking-wider text-[10px]">How to interpret{title ? ` (for ${title})` : ''}:</strong>
                                        <ul className="space-y-1 pl-1">
                                            <li className="text-emerald-400 font-medium">✓ Good: <span className="text-slate-300 font-normal">{goodVsBad.good}</span></li>
                                            <li className="text-rose-400 font-medium">✗ Bad: <span className="text-slate-300 font-normal">{goodVsBad.bad}</span></li>
                                        </ul>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                );
            };

            function App() {
                const [seasons, setSeasons] = React.useState([]);
                const [allTeams, setAllTeams] = React.useState([]);
                const [globalSeason, setGlobalSeason] = React.useState("ALL");
                const [globalTeam, setGlobalTeam] = React.useState("ALL");

                const [h2hTeamA, setH2hTeamA] = React.useState("Arsenal");
                const [h2hTeamB, setH2hTeamB] = React.useState("Chelsea");
                const [h2hMetric, setH2hMetric] = React.useState("fouls_committed");

                const [momentumSeason, setMomentumSeason] = React.useState(["ALL"]);
                const [eloSeason, setEloSeason] = React.useState("ALL");
                const [teamAvailableSeasons, setTeamAvailableSeasons] = React.useState([]);

                const [masterData, setMasterData] = React.useState(null);
                const [loading, setLoading] = React.useState(true);

                const [modalTeam, setModalTeam] = React.useState(null);
                const [teamDetails, setTeamDetails] = React.useState([]);

                React.useEffect(() => {
                    Promise.all([
                        fetch('/api/seasons').then(res => res.json()),
                        fetch('/api/teams').then(res => res.json())
                    ]).then(([seas, teams]) => {
                        setSeasons(seas);
                        setAllTeams(teams);
                        if (teams.length >= 2) {
                            setH2hTeamA(teams[0]);
                            setH2hTeamB(teams[1]);
                        }
                    });
                }, []);

                React.useEffect(() => {
                    if (globalTeam && globalTeam !== "ALL") {
                        setH2hTeamA(globalTeam);
                        fetch(`/api/team-seasons?team_name=${encodeURIComponent(globalTeam)}`)
                            .then(res => res.json())
                            .then(codes => setTeamAvailableSeasons(codes));
                    } else {
                        setTeamAvailableSeasons([]);
                    }
                }, [globalTeam]);

                React.useEffect(() => {
                    setLoading(true);
                    const momParam = momentumSeason.includes("ALL") ? "ALL" : momentumSeason.join(",");
                    fetch(`/api/dashboard-master?season=${globalSeason}&team=${encodeURIComponent(globalTeam)}&h2h_a=${encodeURIComponent(h2hTeamA)}&h2h_b=${encodeURIComponent(h2hTeamB)}&momentum_seasons=${encodeURIComponent(momParam)}&elo_season=${eloSeason}`)
                        .then(res => res.json())
                        .then(data => {
                            setMasterData(data);
                            setLoading(false);
                        });
                }, [globalSeason, globalTeam, h2hTeamA, h2hTeamB, momentumSeason, eloSeason]);

                React.useEffect(() => {
                    if (!masterData) return;

                    const timer = setTimeout(() => {
                        renderH2hDensity(masterData.h2h.matches, h2hTeamA);
                        renderH2hTrajectory(masterData.h2h.trajectory, h2hTeamA, h2hTeamB);
                        renderH2hVariance(masterData.h2h.matches, h2hTeamA);
                        renderH2hStyleParallel(masterData.h2h.style, h2hTeamA, h2hTeamB);
                        renderH2hDisciplineChart(masterData.h2h.discipline, h2hTeamA, h2hMetric);

                        renderQuadrant(masterData.quadrant, globalTeam);
                        renderEloLogistic(masterData.elo, globalTeam);
                        renderShotFunnel(masterData.funnel, globalTeam);
                        renderSterilePossession(masterData.possession, globalTeam);
                        renderHalftimeResilience(masterData.halftime, globalTeam);
                        renderDisciplineChaos(masterData.chaos, globalTeam);
                        renderMomentum(masterData.momentum);
                    }, 100);

                    return () => clearTimeout(timer);
                }, [masterData, h2hMetric]);

                const handleTeamClick = (teamName) => {
                    setModalTeam(teamName);
                    const targetSeason = globalSeason !== "ALL" ? globalSeason : (seasons[0] ? seasons[0].code : "2425");
                    fetch(`/api/team-details?team_name=${encodeURIComponent(teamName)}&season=${targetSeason}`)
                        .then(res => res.json())
                        .then(data => setTeamDetails(data));
                };

                const renderH2hDensity = (matches, teamA) => {
                    const el = document.getElementById('chart-h2h-density');
                    if (!el) return;
                    const diffs = matches.map(m => m.team_a_goal_diff);
                    const trace = { x: diffs, type: 'histogram', autobinx: false, xbins: { start: -6, end: 6, size: 1 }, marker: { color: '#38bdf8', opacity: 0.8 } };
                    Plotly.react(el, [trace], { paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: { color: '#f8fafc' }, xaxis: { title: `${teamA} Goal Differential`, gridcolor: '#1f2937' }, yaxis: { title: 'Frequency', gridcolor: '#1f2937' }, margin: { t: 20, r: 20, b: 50, l: 50 }, autosize: true }, { responsive: true });
                };

                const renderH2hTrajectory = (trajectory, teamA, teamB) => {
                    const el = document.getElementById('chart-h2h-trajectory');
                    if (!el) return;
                    const teamAData = trajectory.filter(t => t.team_name.toLowerCase().includes(teamA.toLowerCase())).sort((a, b) => parseInt(a.season_code, 10) - parseInt(b.season_code, 10));
                    const teamBData = trajectory.filter(t => t.team_name.toLowerCase().includes(teamB.toLowerCase())).sort((a, b) => parseInt(a.season_code, 10) - parseInt(b.season_code, 10));

                    const traceA = { x: teamAData.map(t => t.season_label), y: teamAData.map(t => t.avg_xg), name: teamA, mode: 'lines+markers', line: { color: '#38bdf8', width: 3 } };
                    const traceB = { x: teamBData.map(t => t.season_label), y: teamBData.map(t => t.avg_xg), name: teamB, mode: 'lines+markers', line: { color: '#818cf8', width: 3 } };
                    Plotly.react(el, [traceA, traceB], { paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: { color: '#f8fafc' }, xaxis: { title: 'Season', type: 'category', categoryorder: 'category ascending', gridcolor: '#1f2937' }, yaxis: { title: 'Avg xG', gridcolor: '#1f2937' }, legend: { orientation: 'h', y: 1.15 }, margin: { t: 30, r: 20, b: 50, l: 50 }, autosize: true }, { responsive: true });
                };

                const renderH2hVariance = (matches, teamA) => {
                    const el = document.getElementById('chart-h2h-variance');
                    if (!el) return;
                    const trace = { x: matches.map(m => m.team_a_xg_diff), y: matches.map(m => m.team_a_goal_diff), text: matches.map(m => `${m.season_label}: ${m.home_team} vs ${m.away_team}`), mode: 'markers', marker: { size: 10, color: '#a855f7', opacity: 0.85 } };
                    Plotly.react(el, [trace], { paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: { color: '#f8fafc' }, xaxis: { title: 'xG Advantage', gridcolor: '#1f2937', zerolinecolor: '#475569' }, yaxis: { title: 'Goal Diff', gridcolor: '#1f2937', zerolinecolor: '#475569' }, margin: { t: 20, r: 20, b: 50, l: 50 }, autosize: true }, { responsive: true });
                };

                const renderH2hStyleParallel = (style, teamA, teamB) => {
                    const el = document.getElementById('chart-h2h-parallel');
                    if (!el || !style || style.length === 0) return;
                    const dimensions = [
                        { label: 'Possession %', values: style.map(s => s.possession) },
                        { label: 'Shots', values: style.map(s => s.shots) },
                        { label: 'Shots on Target', values: style.map(s => s.shots_on_target) },
                        { label: 'xG / Shot', values: style.map(s => s.xg_per_shot) }
                    ];
                    const trace = { type: 'parcoords', line: { color: style.map(s => s.team_name.toLowerCase().includes(teamA.toLowerCase()) ? 0 : 1), colorscale: [[0, '#38bdf8'], [1, '#818cf8']] }, dimensions: dimensions };
                    Plotly.react(el, [trace], { paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: { color: '#f8fafc' }, margin: { t: 40, r: 40, b: 30, l: 40 }, autosize: true }, { responsive: true });
                };

                const renderH2hDisciplineChart = (data, teamA, metricKey) => {
                    const el = document.getElementById('chart-h2h-discipline');
                    if (!el || !data || data.length === 0) return;
                    const wins = data.filter(d => d.result === 'W');
                    const draws = data.filter(d => d.result === 'D');
                    const losses = data.filter(d => d.result === 'L');

                    const getXVal = (d) => metricKey === 'yellow_cards' ? d.yellow_cards : (metricKey === 'red_cards' ? d.red_cards : d.fouls_committed);
                    const metricLabel = metricKey === 'yellow_cards' ? 'Yellow Cards' : (metricKey === 'red_cards' ? 'Red Cards' : 'Fouls Committed');

                    const createTrace = (group, name, color) => ({
                        x: group.map(d => getXVal(d)), y: group.map(d => d.xg_diff),
                        text: group.map(d => `${d.season_label} (${d.venue}): ${d.fouls_committed} Fouls, ${d.yellow_cards} Yel, ${d.red_cards} Red`),
                        mode: 'markers', name: `${teamA} ${name}`, marker: { size: 11, color: color, opacity: 0.85 }
                    });

                    Plotly.react(el, [createTrace(wins, 'Wins', '#34d399'), createTrace(draws, 'Draws', '#f59e0b'), createTrace(losses, 'Losses', '#f87171')], {
                        paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: { color: '#f8fafc' },
                        xaxis: { title: `${teamA} ${metricLabel} (per match)`, gridcolor: '#1f2937' },
                        yaxis: { title: `${teamA} xG Advantage`, gridcolor: '#1f2937', zerolinecolor: '#475569' },
                        legend: { orientation: 'h', y: 1.15 }, margin: { t: 30, r: 20, b: 50, l: 50 }, autosize: true
                    }, { responsive: true });
                };

                const renderQuadrant = (data, team) => {
                    const el = document.getElementById('chart-quadrant');
                    if (!el) return;
                    const xVals = team === "ALL" ? data.map(d => d.team_name) : data.map(d => d.season_label);
                    const trace = { x: data.map(d => d.avg_xg_diff), y: data.map(d => d.avg_goal_diff), text: xVals, mode: 'markers+text', textposition: 'top center', marker: { size: 12, color: '#38bdf8', opacity: 0.85 } };
                    Plotly.react(el, [trace], { paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: { color: '#f8fafc' }, xaxis: { title: 'xG Difference', gridcolor: '#1f2937', zerolinecolor: '#475569' }, yaxis: { title: 'Goal Difference', gridcolor: '#1f2937', zerolinecolor: '#475569' }, margin: { t: 20, r: 20, b: 50, l: 50 }, autosize: true }, { responsive: true });
                    if (team === "ALL") el.on('plotly_click', (d) => d.points && handleTeamClick(d.points[0].text));
                };

                const renderEloLogistic = (data, team) => {
                    const el = document.getElementById('chart-elo-logistic');
                    if (!el) return;
                    const trace = { x: data.map(d => d.elo_diff), y: data.map(d => d.match_outcome_val), text: data.map(d => `${d.season_label}: ${d.home_team} vs ${d.away_team}`), mode: 'markers', marker: { size: 9, color: '#38bdf8', opacity: 0.7 } };
                    Plotly.react(el, [trace], { paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: { color: '#f8fafc' }, xaxis: { title: 'Elo Advantage', gridcolor: '#1f2937', zerolinecolor: '#475569' }, yaxis: { title: 'Outcome', gridcolor: '#1f2937', zerolinecolor: '#475569' }, margin: { t: 20, r: 20, b: 50, l: 50 }, autosize: true }, { responsive: true });
                };

                const renderShotFunnel = (data, team) => {
                    const el = document.getElementById('chart-funnel');
                    if (!el) return;
                    const xVals = team === "ALL" ? data.slice(0, 10).map(d => d.team_name) : data.map(d => d.season_label);
                    Plotly.react(el, [
                        { x: xVals, y: data.map(d => d.total_shots), name: 'Shots', type: 'bar', marker: { color: '#64748b' } },
                        { x: xVals, y: data.map(d => d.shots_on_target), name: 'On Target', type: 'bar', marker: { color: '#818cf8' } },
                        { x: xVals, y: data.map(d => d.total_xg), name: 'xG', type: 'bar', marker: { color: '#38bdf8' } },
                        { x: xVals, y: data.map(d => d.total_goals), name: 'Actual Goals', type: 'bar', marker: { color: '#34d399' } }
                    ], { 
                        barmode: 'group', 
                        paper_bgcolor: 'transparent', 
                        plot_bgcolor: 'transparent', 
                        font: { color: '#f8fafc' }, 
                        xaxis: { tickangle: -45, gridcolor: 'transparent' }, 
                        yaxis: { title: 'Volume', gridcolor: '#1f2937' }, 
                        legend: { orientation: 'h', y: 1.15 }, 
                        margin: { t: 30, r: 20, b: 80, l: 50 }, 
                        autosize: true 
                    }, { responsive: true });
                };

                const renderSterilePossession = (data, team) => {
                    const el = document.getElementById('chart-possession');
                    if (!el) return;
                    const trace = { x: data.map(d => d.avg_possession), y: data.map(d => d.penetration_efficiency), text: team === "ALL" ? data.map(d => d.team_name) : data.map(d => d.season_label), mode: 'markers+text', textposition: 'top center', marker: { size: 12, color: '#a855f7', opacity: 0.85 } };
                    Plotly.react(el, [trace], { paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: { color: '#f8fafc' }, xaxis: { title: 'Possession %', gridcolor: '#1f2937' }, yaxis: { title: 'Penetration Ratio', gridcolor: '#1f2937' }, margin: { t: 20, r: 20, b: 50, l: 60 }, autosize: true }, { responsive: true });
                    if (team === "ALL") el.on('plotly_click', (d) => d.points && handleTeamClick(d.points[0].text));
                };

                const renderHalftimeResilience = (data, team) => {
                    const el = document.getElementById('chart-halftime');
                    if (!el) return;
                    const sorted = team === "ALL" ? [...data].sort((a, b) => b.halftime_comebacks - a.halftime_comebacks).slice(0, 10) : data;
                    const xVals = team === "ALL" ? sorted.map(d => d.team_name) : sorted.map(d => d.season_label);
                    Plotly.react(el, [
                        { x: xVals, y: sorted.map(d => d.halftime_comebacks), name: 'Comebacks', type: 'bar', marker: { color: '#34d399' } },
                        { x: xVals, y: sorted.map(d => d.leads_blown), name: 'Leads Blown', type: 'bar', marker: { color: '#f87171' } }
                    ], { barmode: 'group', paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: { color: '#f8fafc' }, xaxis: { tickangle: -45, gridcolor: 'transparent' }, yaxis: { title: 'Matches', gridcolor: '#1f2937' }, legend: { orientation: 'h', y: 1.15 }, margin: { t: 30, r: 20, b: 80, l: 40 }, autosize: true }, { responsive: true });
                };

                const renderDisciplineChaos = (data, team) => {
                    const el = document.getElementById('chart-chaos');
                    if (!el) return;
                    const trace = { x: data.map(d => d.defensive_workload), y: data.map(d => d.chaos_index), text: team === "ALL" ? data.map(d => d.team_name) : data.map(d => d.season_label), mode: 'markers+text', textposition: 'top center', marker: { size: 12, color: '#f59e0b', opacity: 0.85 } };
                    Plotly.react(el, [trace], { paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: { color: '#f8fafc' }, xaxis: { title: 'Defensive Workload', gridcolor: '#1f2937' }, yaxis: { title: 'Chaos Index', gridcolor: '#1f2937' }, margin: { t: 20, r: 20, b: 50, l: 60 }, autosize: true }, { responsive: true });
                    if (team === "ALL") el.on('plotly_click', (d) => d.points && handleTeamClick(d.points[0].text));
                };

                const renderMomentum = (data) => {
                    const el = document.getElementById('chart-momentum');
                    if (!el) return;
                    if (!data || data.length === 0) {
                        Plotly.purge(el);
                        return;
                    }
                    const tracesMap = {};
                    data.forEach(d => {
                        const seasonStr = String(d.season_code || '');
                        const formattedSeason = seasonStr.length === 4 ? `20${seasonStr.slice(0,2)}/${seasonStr.slice(2)}` : seasonStr;
                        const key = `${d.team_name} (${formattedSeason})`;
                        if (!tracesMap[key]) tracesMap[key] = { x: [], y: [] };
                        tracesMap[key].x.push(Number(d.normalized_date));
                        tracesMap[key].y.push(Number(d.rolling_value));
                    });
                    const traces = Object.keys(tracesMap).map(key => ({
                        x: tracesMap[key].x, y: tracesMap[key].y, mode: 'lines+markers', name: key, line: { width: 2.5 }, marker: { size: 4 }
                    }));
                    Plotly.react(el, traces, {
                        paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: { color: '#f8fafc' },
                        xaxis: { title: 'Match Week (1 - 38)', gridcolor: '#1f2937' },
                        yaxis: { title: 'Rolling 5-Match xG', gridcolor: '#1f2937' },
                        legend: { orientation: 'h', y: 1.15 }, margin: { t: 40, r: 20, b: 40, l: 40 }, autosize: true
                    }, { responsive: true });
                };

                return (
                    <div className="min-h-screen pb-24 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-slate-950 to-black text-slate-100">
                        
                        {/* GLOBAL MASTER HEADER & CONTROLS */}
                        <header className="sticky top-0 z-40 bg-slate-950/85 backdrop-blur-md border-b border-slate-800/80 px-6 py-4 shadow-xl">
                            <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
                                <div className="flex items-center gap-3">
                                    <span className={`w-3 h-3 rounded-full transition-colors ${loading ? 'bg-amber-500 animate-ping' : 'bg-sky-500 shadow-lg shadow-sky-500/50'}`}></span>
                                    <div>
                                        <h1 className="text-xl font-black tracking-tight text-white flex items-center gap-2">
                                            PL Analytics Engine
                                            {loading && <span className="text-[10px] text-amber-400 font-mono bg-amber-500/10 px-2 py-0.5 rounded-full border border-amber-500/20">Updating...</span>}
                                        </h1>
                                    </div>
                                </div>
                                
                                <div className="flex flex-wrap items-center gap-3">
                                    <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-xl shadow-inner">
                                        <label className="text-[11px] font-bold text-slate-400 uppercase">Season</label>
                                        <select value={globalSeason} onChange={(e) => setGlobalSeason(e.target.value)} className="bg-transparent text-slate-100 text-xs font-semibold focus:outline-none">
                                            <option value="ALL">All Seasons</option>
                                            {seasons.map(s => <option key={s.code} value={s.code}>{s.label}</option>)}
                                        </select>
                                    </div>
                                    <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-xl shadow-inner">
                                        <label className="text-[11px] font-bold text-slate-400 uppercase">Team Filter</label>
                                        <select value={globalTeam} onChange={(e) => setGlobalTeam(e.target.value)} className="bg-transparent text-slate-100 text-xs font-semibold focus:outline-none max-w-[140px]">
                                            <option value="ALL">All Teams</option>
                                            {allTeams.map(t => <option key={t} value={t}>{t}</option>)}
                                        </select>
                                    </div>
                                    <nav className="hidden lg:flex items-center gap-1 bg-slate-900/90 border border-slate-800 p-1 rounded-xl">
                                        <a href="#chapter-1" className="px-3 py-1 rounded-lg text-xs font-semibold text-sky-400 hover:bg-slate-800 transition-all">Ch.1 H2H</a>
                                        <a href="#chapter-2" className="px-3 py-1 rounded-lg text-xs font-semibold text-indigo-400 hover:bg-slate-800 transition-all">Ch.2 Efficiency</a>
                                        <a href="#chapter-3" className="px-3 py-1 rounded-lg text-xs font-semibold text-amber-400 hover:bg-slate-800 transition-all">Ch.3 Momentum</a>
                                    </nav>
                                </div>
                            </div>
                        </header>

                        {/* ACTIVE FILTER BANNER */}
                        <div className="bg-slate-900/60 border-b border-slate-800/60 py-2.5 px-6">
                            <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between text-xs text-slate-300 gap-4">
                                <div className="flex items-center gap-4">
                                    <span className="font-bold text-slate-400 uppercase tracking-wider text-[10px]">Active Scope:</span>
                                    <span className="bg-sky-500/10 text-sky-400 px-2.5 py-1 rounded-lg border border-sky-500/20 font-semibold">
                                        Season: {formatSeasonLabel(globalSeason, seasons)}
                                    </span>
                                    <span className="bg-indigo-500/10 text-indigo-400 px-2.5 py-1 rounded-lg border border-indigo-500/20 font-semibold">
                                        Team: {globalTeam === "ALL" ? "All Clubs Compared" : globalTeam}
                                    </span>
                                </div>
                                <div className="text-slate-400 text-[11px]">
                                    Tip: Chapter 1 Team A automatically syncs to your global team filter choice.
                                </div>
                            </div>
                        </div>

                        <div className="max-w-7xl mx-auto px-6 pt-10 space-y-16">

                            {/* CHAPTER 1: RIVALRY HISTORY */}
                            <section id="chapter-1" className="scroll-mt-24 bg-slate-900/40 backdrop-blur-md border border-slate-800/80 rounded-3xl p-8 shadow-2xl relative overflow-hidden">
                                <div className="absolute top-0 right-0 w-96 h-96 bg-sky-500/5 rounded-full blur-3xl pointer-events-none"></div>
                                <div className="flex items-center justify-between mb-3">
                                    <span className="px-3 py-1 text-[11px] font-extrabold uppercase tracking-widest bg-sky-500/10 text-sky-400 border border-sky-500/20 rounded-full">
                                        Chapter 1 of 3 • Rivalry History
                                    </span>
                                    <span className="text-xs text-slate-400 font-mono">Multi-Season Suite</span>
                                </div>
                                <h2 className="text-3xl font-extrabold text-white mb-2">Cross-Era Rivalry Diagnostics</h2>
                                <p className="text-slate-400 text-sm max-w-3xl mb-8">
                                    Evaluate historical head-to-head fixtures between <strong className="text-sky-400">{h2hTeamA}</strong> and <strong className="text-indigo-400">{h2hTeamB}</strong> across margin distributions, multi-decade xG trajectories, variance scatter, and disciplinary impact models.
                                </p>

                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8 bg-slate-950/60 border border-slate-800/60 p-4 rounded-2xl shadow-inner">
                                    <div className="flex flex-col gap-1.5">
                                        <label className="text-[11px] font-bold text-slate-400 uppercase">Team A (Synced to Global Team Filter)</label>
                                        <select value={h2hTeamA} onChange={(e) => setH2hTeamA(e.target.value)} className="bg-slate-900 text-slate-100 border border-slate-700 px-3 py-2.5 rounded-xl text-sm font-semibold">
                                            {allTeams.map(t => <option key={t} value={t}>{t}</option>)}
                                        </select>
                                    </div>
                                    <div className="flex flex-col gap-1.5">
                                        <label className="text-[11px] font-bold text-slate-400 uppercase">Team B (Rival)</label>
                                        <select value={h2hTeamB} onChange={(e) => setH2hTeamB(e.target.value)} className="bg-slate-900 text-slate-100 border border-slate-700 px-3 py-2.5 rounded-xl text-sm font-semibold">
                                            {allTeams.map(t => <option key={t} value={t}>{t}</option>)}
                                        </select>
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                    <div className="bg-slate-950/80 border border-slate-800/80 rounded-2xl p-5 flex flex-col justify-between shadow-lg">
                                        <div>
                                            <h3 className="text-sm font-bold text-sky-400 mb-1">1. Match Goal Margin Distribution ({h2hTeamA})</h3>
                                            <div id="chart-h2h-density" className="w-full h-[300px]"></div>
                                        </div>
                                        <InfoAccordion title={h2hTeamA} whatIsIt="Histogram showing how often matches end in specific goal differentials." goodVsBad={{ good: "Bars heavily skewed to positive numbers (+1, +2, +3+), showing consistent multi-goal victories.", bad: "Bars skewed to negative numbers (-1, -2, -3+), showing frequent multi-goal losses." }} />
                                    </div>

                                    <div className="bg-slate-950/80 border border-slate-800/80 rounded-2xl p-5 flex flex-col justify-between shadow-lg">
                                        <div>
                                            <h3 className="text-sm font-bold text-sky-400 mb-1">2. Multi-Decade xG Trajectory</h3>
                                            <div id="chart-h2h-trajectory" className="w-full h-[300px]"></div>
                                        </div>
                                        <InfoAccordion title={h2hTeamA} whatIsIt="Season-by-season average Expected Goals (xG) created in matches between these rivals over time." goodVsBad={{ good: "Your team's line consistently trending upward or remaining above your opponent's line.", bad: "Your team's line dipping below the rival's line, signifying a loss in chance-creation dominance." }} />
                                    </div>

                                    <div className="bg-slate-950/80 border border-slate-800/80 rounded-2xl p-5 flex flex-col justify-between shadow-lg">
                                        <div>
                                            <h3 className="text-sm font-bold text-purple-400 mb-1">3. H2H Variance Scatter</h3>
                                            <div id="chart-h2h-variance" className="w-full h-[300px]"></div>
                                        </div>
                                        <InfoAccordion title={h2hTeamA} whatIsIt="Pits xG Advantage (X-axis) against actual Goal Difference (Y-axis) for each derby match." goodVsBad={{ good: "Nodes in the top-right quadrant (winning xG and winning the match) or above the center line.", bad: "Nodes in the bottom-right quadrant (outshooting the rival in xG but still losing the match)." }} />
                                    </div>

                                    <div className="bg-slate-950/80 border border-slate-800/80 rounded-2xl p-5 flex flex-col justify-between shadow-lg">
                                        <div>
                                            <h3 className="text-sm font-bold text-indigo-400 mb-1">4. Tactical Style Matchup Dimensions</h3>
                                            <div id="chart-h2h-parallel" className="w-full h-[300px]"></div>
                                        </div>
                                        <InfoAccordion title={h2hTeamA} whatIsIt="Parallel coordinates mapping possession, total shots, shots on target, and xG per shot head-to-head." goodVsBad={{ good: "Lines staying high across shot volume and xG/shot, showing control and high-quality chances.", bad: "Lines dropping low across metrics, indicating low ball retention and inefficient shot selection." }} />
                                    </div>
                                </div>

                                <div className="bg-slate-950/80 border border-slate-800/80 rounded-2xl p-5 mt-6 shadow-lg">
                                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
                                        <div>
                                            <h3 className="text-sm font-bold text-amber-400 mb-1">5. Head-to-Head Disciplinary Metric vs. Match Outcome & xG Differential</h3>
                                            <p className="text-slate-400 text-xs">Maps every H2H fixture: inspect how fouls, yellows, or red cards impact win rates and expected goal advantages.</p>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <label className="text-[11px] font-bold text-slate-400 uppercase">Metric</label>
                                            <select value={h2hMetric} onChange={(e) => setH2hMetric(e.target.value)} className="bg-slate-900 text-slate-100 border border-slate-700 px-3 py-1.5 rounded-xl text-xs font-semibold">
                                                <option value="fouls_committed">Fouls Committed</option>
                                                <option value="yellow_cards">Yellow Cards</option>
                                                <option value="red_cards">Red Cards</option>
                                            </select>
                                        </div>
                                    </div>
                                    <div id="chart-h2h-discipline" className="w-full h-[350px]"></div>
                                    <InfoAccordion title={h2hTeamA} whatIsIt="Match-by-match scatter plot mapping disciplinary metric count (X-axis) against xG Advantage (Y-axis), color-coded by match result." goodVsBad={{ good: "Green dots (wins) sitting at low-to-moderate foul/card counts with positive xG advantages.", bad: "Red dots (losses) clustered at high foul or red card counts with negative xG advantages." }} />
                                </div>
                            </section>

                            {/* CHAPTER 2: CAMPAIGN EFFICIENCY & STYLE */}
                            <section id="chapter-2" className="scroll-mt-24 bg-slate-900/40 backdrop-blur-md border border-slate-800/80 rounded-3xl p-8 shadow-2xl relative overflow-hidden space-y-8">
                                <div className="absolute top-0 right-0 w-96 h-96 bg-indigo-500/5 rounded-full blur-3xl pointer-events-none"></div>
                                <div>
                                    <span className="px-3 py-1 text-[11px] font-extrabold uppercase tracking-widest bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 rounded-full">
                                        Chapter 2 of 3 • Season Metrics
                                    </span>
                                    <h2 className="text-3xl font-extrabold text-white mt-3 mb-2">Campaign Efficiency & Tactical Style</h2>
                                    <p className="text-slate-400 text-sm max-w-3xl">
                                        Currently viewing metrics for season <strong className="text-sky-400">{formatSeasonLabel(globalSeason, seasons)}</strong> {globalTeam !== "ALL" ? `focused on team ${globalTeam}` : "(All Clubs Compared)"}. Separate underlying chance creation from finishing luck.
                                    </p>
                                </div>

                                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                                    <div className="bg-slate-950/80 border border-slate-800/80 rounded-3xl p-6 shadow-xl flex flex-col justify-between">
                                        <div>
                                            <h2 className="text-xl font-bold text-slate-100 mb-1">Tactical Quality vs. Outcome Variance</h2>
                                            <p className="text-slate-300 text-xs mb-2">True dominance is revealed when expected goal differentials outpace actual goal differentials. Click any team node to inspect their match log.</p>
                                            <div className="bg-slate-900/40 border border-slate-800/60 rounded-2xl p-3 mt-4">
                                                <div id="chart-quadrant" className="w-full h-[400px]"></div>
                                            </div>
                                        </div>
                                        <InfoAccordion whatIsIt="Pits average Expected Goal Difference (X-axis) against actual Goal Difference (Y-axis) per match." goodVsBad={{ good: "Top-Right quadrant: generating better xG chance quality than opponents and successfully translating it into positive goal margins.", bad: "Bottom-Left quadrant: negative chance creation paired with negative goal outcomes." }} />
                                    </div>

                                    <div className="bg-slate-950/80 border border-slate-800/80 rounded-3xl p-6 shadow-xl flex flex-col justify-between">
                                        <div>
                                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
                                                <div>
                                                    <h2 className="text-xl font-bold text-slate-100">Elo Dynamics & Win Probability</h2>
                                                    <p className="text-slate-300 text-xs">Pre-market ratings estimate team strength against actual match realizations.</p>
                                                </div>
                                                <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 px-2.5 py-1 rounded-xl shadow-inner">
                                                    <label className="text-[10px] font-bold text-slate-400 uppercase">Season</label>
                                                    <select value={eloSeason} onChange={(e) => setEloSeason(e.target.value)} className="bg-transparent text-sky-400 text-xs font-semibold focus:outline-none">
                                                        <option value="ALL">All Seasons</option>
                                                        {seasons.map(s => <option key={s.code} value={s.code}>{s.label}</option>)}
                                                    </select>
                                                </div>
                                            </div>
                                            <div className="bg-slate-900/40 border border-slate-800/60 rounded-2xl p-3 mt-4">
                                                <div id="chart-elo-logistic" className="w-full h-[400px]"></div>
                                            </div>
                                        </div>
                                        <InfoAccordion whatIsIt="Pre-match Elo Rating Advantage (X-axis) plotted against actual match outcomes (Y-axis: 1.0 Win, 0.5 Draw, 0.0 Loss)." goodVsBad={{ good: "Outcomes at 1.0 when Elo differential is positive (winning expected matches) or points at 1.0 with negative Elo (upsetting stronger teams).", bad: "Outcomes at 0.0 when holding a strong positive Elo differential (suffering upset losses)." }} />
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                                    <div className="bg-slate-950/80 border border-slate-800/80 rounded-3xl p-6 shadow-xl flex flex-col justify-between">
                                        <div>
                                            <h2 className="text-xl font-bold text-slate-100 mb-1">Shot Funnel & Selection Efficiency</h2>
                                            <p className="text-slate-300 text-xs mb-2">Generating high shot volume means little without accuracy and shot quality. The funnel contrasts raw shots against shots on target, expected goals, and actual goals.</p>
                                            <div className="bg-slate-900/40 border border-slate-800/60 rounded-2xl p-3 mt-4">
                                                <div id="chart-funnel" className="w-full h-[400px]"></div>
                                            </div>
                                        </div>
                                        <InfoAccordion whatIsIt="Grouped bar chart detailing the conversion sequence from Total Shots -> Shots on Target -> Total xG -> Actual Goals." goodVsBad={{ good: "High ratio of Shots on Target relative to Total Shots, combined with actual goals outperforming total xG.", bad: "Massive Total Shot volume with low Shots on Target and low actual goals, signaling finishing inefficiency." }} />
                                    </div>

                                    <div className="bg-slate-950/80 border border-slate-800/80 rounded-3xl p-6 shadow-xl flex flex-col justify-between">
                                        <div>
                                            <h2 className="text-xl font-bold text-slate-100 mb-1">Territorial Control vs. Sterile Possession</h2>
                                            <p className="text-slate-300 text-xs mb-2">Not all possession is equal. This scatter exposes sides that dominate ball retention in harmless areas versus direct outfits converting entries into box touches.</p>
                                            <div className="bg-slate-900/40 border border-slate-800/60 rounded-2xl p-3 mt-4">
                                                <div id="chart-possession" className="w-full h-[400px]"></div>
                                            </div>
                                        </div>
                                        <InfoAccordion whatIsIt="Possession % (X-axis) vs. Penetration Efficiency (Opposition Box Touches / Final Third Entries) on the Y-axis." goodVsBad={{ good: "Top-Right quadrant: commanding high possession while effectively turning territory into box penetration.", bad: "Bottom-Right quadrant: high possession % with very low penetration ratio ('sterile possession')." }} />
                                    </div>
                                </div>
                            </section>

                            {/* CHAPTER 3: PRESSURE, RESILIENCE & MOMENTUM */}
                            <section id="chapter-3" className="scroll-mt-24 bg-slate-900/40 backdrop-blur-md border border-slate-800/80 rounded-3xl p-8 shadow-2xl relative overflow-hidden space-y-8">
                                <div className="absolute top-0 right-0 w-96 h-96 bg-amber-500/5 rounded-full blur-3xl pointer-events-none"></div>
                                <div>
                                    <span className="px-3 py-1 text-[11px] font-extrabold uppercase tracking-widest bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded-full">
                                        Chapter 3 of 3 • Momentum & Resilience
                                    </span>
                                    <h2 className="text-3xl font-extrabold text-white mt-3 mb-2">Pressure, Resilience & Season Momentum</h2>
                                    <p className="text-slate-400 text-sm max-w-3xl">
                                        Examine locker-room adaptability under pressure, disciplinary risk during defensive workloads, and rolling 5-match chronological trajectories.
                                    </p>
                                </div>

                                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                                    <div className="bg-slate-950/80 border border-slate-800/80 rounded-3xl p-6 shadow-xl flex flex-col justify-between">
                                        <div>
                                            <h2 className="text-xl font-bold text-slate-100 mb-1">Half-Time Adaptability & Comebacks</h2>
                                            <p className="text-slate-300 text-xs mb-2">Managerial acumen shines in the locker room at intermission. Tallies successful half-time deficit turnarounds against leads squandered.</p>
                                            <div className="bg-slate-900/40 border border-slate-800/60 rounded-2xl p-3 mt-4">
                                                <div id="chart-halftime" className="w-full h-[400px]"></div>
                                            </div>
                                        </div>
                                        <InfoAccordion whatIsIt="Bar chart comparing Second-Half Comebacks (winning after trailing at half-time) vs. Leads Blown (losing after leading at half-time)." goodVsBad={{ good: "High green bars (Comebacks) and zero or low red bars (Leads Blown), demonstrating halftime adjustment and game management.", bad: "High red bars (Leads Blown) paired with zero comebacks, showing second-half collapses and poor game management." }} />
                                    </div>

                                    <div className="bg-slate-950/80 border border-slate-800/80 rounded-3xl p-6 shadow-xl flex flex-col justify-between">
                                        <div>
                                            <h2 className="text-xl font-bold text-slate-100 mb-1">Discipline, Pressure & Match Chaos</h2>
                                            <p className="text-slate-300 text-xs mb-2">High-pressing defensive systems generate immense defensive workload, but often cross the line into foul trouble. The chaos index measures whether pressure is disciplined.</p>
                                            <div className="bg-slate-900/40 border border-slate-800/60 rounded-2xl p-3 mt-4">
                                                <div id="chart-chaos" className="w-full h-[400px]"></div>
                                            </div>
                                        </div>
                                        <InfoAccordion whatIsIt="Defensive Workload / Opponent Final Third Entries (X-axis) vs. Chaos Index weighted disciplinary sum (Y-axis)." goodVsBad={{ good: "Low Chaos Index relative to workload, showing clean defensive structure under pressure.", bad: "High Chaos Index (top-left or top-right), indicating panic fouls, card accumulation, and reckless defensive actions under strain." }} />
                                    </div>
                                </div>

                                <div className="bg-slate-950/80 border border-slate-800/80 rounded-3xl p-6 shadow-xl">
                                    <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-6">
                                        <div>
                                            <h2 className="text-2xl font-bold text-slate-100 mb-1">Season Momentum & Time-Series Progression</h2>
                                            <p className="text-slate-300 text-xs">
                                                Plotting rolling 5-match expected goals across Match Weeks 1-38 <strong className="text-sky-400">for {globalTeam === "ALL" ? "All Clubs (Top 8 comparative)" : globalTeam}</strong>.
                                            </p>
                                        </div>
                                        <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
                                            <button onClick={() => setMomentumSeason(["ALL"])} className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${momentumSeason.includes("ALL") ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/25' : 'bg-slate-900 text-slate-400 border border-slate-800 hover:bg-slate-800'}`}>All Seasons</button>
                                            {seasons.filter(s => globalTeam === "ALL" || teamAvailableSeasons.includes(s.code)).map(s => {
                                                const isSelected = !momentumSeason.includes("ALL") && momentumSeason.includes(s.code);
                                                return (
                                                    <button key={s.code} onClick={() => {
                                                        if (momentumSeason.includes("ALL")) setMomentumSeason([s.code]);
                                                        else {
                                                            const exists = momentumSeason.includes(s.code);
                                                            const updated = exists ? momentumSeason.filter(c => c !== s.code) : [...momentumSeason, s.code];
                                                            setMomentumSeason(updated.length > 0 ? updated : ["ALL"]);
                                                        }
                                                    }} className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${isSelected ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/25' : 'bg-slate-900 text-slate-400 border border-slate-800 hover:bg-slate-800'}`}>{s.label}</button>
                                                );
                                            })}
                                        </div>
                                    </div>
                                    <div className="bg-slate-900/40 border border-slate-800/60 rounded-2xl p-4">
                                        <div id="chart-momentum" className="w-full h-[450px]"></div>
                                    </div>
                                    <InfoAccordion whatIsIt="Rolling 5-match moving average of Expected Goals (or Actual Goals) across Match Weeks 1-38." goodVsBad={{ good: "Sustained high values or upward trajectory over multi-match stretches, representing peak underlying form.", bad: "Sharp dips or prolonged low plateaus below 1.0 xG, indicating prolonged tactical slumps." }} />
                                </div>
                            </section>

                        </div>

                        {modalTeam && (
                            <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 z-50">
                                <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-2xl w-full p-6 shadow-2xl relative max-h-[85vh] flex flex-col">
                                    <div className="flex items-center justify-between mb-4 border-b border-slate-800 pb-4">
                                        <h3 className="text-xl font-bold text-white">{modalTeam} Match Log</h3>
                                        <button onClick={() => setModalTeam(null)} className="bg-slate-800 text-slate-300 px-3 py-1.5 rounded-xl text-xs font-bold hover:bg-slate-700">Close ✕</button>
                                    </div>
                                    <div className="overflow-y-auto flex-1 pr-1">
                                        <table className="w-full text-left border-collapse text-sm">
                                            <thead>
                                                <tr className="border-b border-slate-800 text-slate-400 font-semibold sticky top-0 bg-slate-900">
                                                    <th className="py-2.5 px-3">Date</th>
                                                    <th className="py-2.5 px-3">Opponent</th>
                                                    <th className="py-2.5 px-3">Venue</th>
                                                    <th className="py-2.5 px-3">Score</th>
                                                    <th className="py-2.5 px-3">xG</th>
                                                    <th className="py-2.5 px-3">Res</th>
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y divide-slate-800/40">
                                                {teamDetails.map((det, i) => (
                                                    <tr key={i} className="hover:bg-slate-800/30">
                                                        <td className="py-2.5 px-3 text-slate-300">{det.match_date}</td>
                                                        <td className="py-2.5 px-3 font-medium text-slate-100">{det.opponent_name}</td>
                                                        <td className="py-2.5 px-3 uppercase text-xs font-bold text-slate-400">{det.venue}</td>
                                                        <td className="py-2.5 px-3 font-mono font-bold text-sky-400">{det.goals_for} - {det.goals_against}</td>
                                                        <td className="py-2.5 px-3 font-mono text-slate-300">{det.xg_for} - {det.xg_against}</td>
                                                        <td className="py-2.5 px-3 font-bold"><span className="px-2 py-0.5 rounded text-xs bg-emerald-500/20 text-emerald-400">{det.result}</span></td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                );
            }

            ReactDOM.render(<App />, document.getElementById('root'));
        </script>
    </body>
    </html>
    """