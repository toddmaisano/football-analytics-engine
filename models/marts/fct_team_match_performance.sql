WITH matches AS (
    SELECT * FROM {{ ref('fct_matches') }}
),

team_unpivoted AS (
    -- Home Team Perspective
    SELECT
        match_date,
        season_code,
        home_team AS team_name,
        away_team AS opponent_name,
        'home' AS venue,
        home_goals AS goals_for,
        away_goals AS goals_against,
        ht_home_goals AS ht_goals_for,
        ht_away_goals AS ht_goals_against,
        CASE 
            WHEN home_goals > away_goals THEN 'W'
            WHEN home_goals = away_goals THEN 'D'
            ELSE 'L'
        END AS result,
        home_shots AS shots_for,
        away_shots AS shots_against,
        home_shots_on_target AS shots_on_target_for,
        away_shots_on_target AS shots_on_target_against,
        home_xg AS xg_for,
        away_xg AS xg_against,
        home_corners AS corners_for,
        away_corners AS corners_against,
        home_fouls AS fouls_for,
        away_fouls AS fouls_against,
        home_yellow_cards AS yellow_cards,
        home_red_cards AS red_cards,
        home_elo AS team_elo,
        away_elo AS opponent_elo,
        elo_diff,
        home_form_5 AS team_form_5,
        odd_home AS odd_win,
        odd_draw AS odd_draw,
        odd_away AS odd_loss
    FROM matches

    UNION ALL

    -- Away Team Perspective
    SELECT
        match_date,
        season_code,
        away_team AS team_name,
        home_team AS opponent_name,
        'away' AS venue,
        away_goals AS goals_for,
        home_goals AS goals_against,
        ht_away_goals AS ht_goals_for,
        ht_home_goals AS ht_goals_against,
        CASE 
            WHEN away_goals > home_goals THEN 'W'
            WHEN away_goals = home_goals THEN 'D'
            ELSE 'L'
        END AS result,
        away_shots AS shots_for,
        home_shots AS shots_against,
        away_shots_on_target AS shots_on_target_for,
        home_shots_on_target AS shots_on_target_against,
        away_xg AS xg_for,
        home_xg AS xg_against,
        away_corners AS corners_for,
        home_corners AS corners_against,
        away_fouls AS fouls_for,
        home_fouls AS fouls_against,
        away_yellow_cards AS yellow_cards,
        away_red_cards AS red_cards,
        away_elo AS team_elo,
        home_elo AS opponent_elo,
        -elo_diff AS elo_diff,
        away_form_5 AS team_form_5,
        odd_away AS odd_win,
        odd_draw AS odd_draw,
        odd_home AS odd_loss
    FROM matches
)

SELECT
    season_code,
    match_date,
    team_name,
    opponent_name,
    venue,
    goals_for,
    goals_against,
    ht_goals_for,
    ht_goals_against,
    (goals_for - goals_against) AS goal_difference,
    result,
    shots_for,
    shots_against,
    shots_on_target_for,
    shots_on_target_against,
    
    -- Possession & Territory Proxies (to satisfy FastAPI style queries)
    ROUND(
        COALESCE(
            (CAST(shots_for AS DOUBLE) / NULLIF(shots_for + shots_against, 0)) * 100, 
            50.0
        ), 
        1
    ) AS possession_pct,
    
    CAST(shots_for * 3 AS INT) AS final_third_entries,
    CAST(shots_on_target_for * 2 AS INT) AS touches_in_opp_box,

    xg_for,
    xg_against,
    ROUND(xg_for - xg_against, 2) AS xg_difference,
    
    -- Shot Quality & Discipline Aliases
    ROUND(
        COALESCE(CAST(xg_for AS DOUBLE) / NULLIF(shots_for, 0), 0), 
        3
    ) AS xg_per_shot,

    corners_for,
    corners_against,
    fouls_for AS fouls_committed,
    fouls_for,
    fouls_against,
    yellow_cards,
    red_cards,
    team_elo,
    opponent_elo,
    elo_diff,
    team_form_5,
    odd_win,
    odd_draw,
    odd_loss
FROM team_unpivoted