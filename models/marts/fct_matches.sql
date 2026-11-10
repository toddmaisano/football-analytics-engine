WITH derived_xg AS (
    SELECT * FROM {{ ref('int_derived_xg') }}
),

gabor_matches AS (
    SELECT * FROM {{ ref('stg_gabor_matches') }}
),

calculated AS (
    SELECT
        dx.season_code,
        dx.match_date,
        dx.home_team,
        dx.away_team,

        -- Goals & Half-time
        e.home_goals,
        e.away_goals,
        e.full_time_result,
        g.ht_home_goals,
        g.ht_away_goals,
        g.ht_result,

        -- Second Half Goals (Calculated Game-State Shift)
        (e.home_goals - COALESCE(g.ht_home_goals, 0)) AS ht2_home_goals,
        (e.away_goals - COALESCE(g.ht_away_goals, 0)) AS ht2_away_goals,

        -- Shot Metrics
        dx.home_shots,
        dx.away_shots,
        dx.home_shots_on_target,
        dx.away_shots_on_target,

        -- xG Proxies & Native
        dx.derived_home_xg,
        dx.derived_away_xg,
        dx.native_home_xg,
        dx.native_away_xg,

        -- Set Pieces & Discipline
        g.home_corners,
        g.away_corners,
        g.home_fouls,
        g.away_fouls,
        g.home_yellow_cards,
        g.away_yellow_cards,
        g.home_red_cards,
        g.away_red_cards,

        -- Elo & Form Context
        g.home_elo,
        g.away_elo,
        ROUND(g.home_elo - g.away_elo, 2) AS elo_diff,
        g.home_form_5,
        g.away_form_5,

        -- Market & Handicap
        g.odd_home,
        g.odd_draw,
        g.odd_away,
        g.handicap_size,
        g.handicap_odd_home,
        g.handicap_odd_away

    FROM derived_xg dx
    JOIN {{ ref('stg_epl_matches') }} e
      ON dx.match_date = e.match_date 
     AND dx.home_team = e.home_team 
     AND dx.away_team = e.away_team
    LEFT JOIN gabor_matches g
        ON dx.match_date = g.match_date
       AND dx.home_team = g.home_team
       AND dx.away_team = g.away_team
)

SELECT
    season_code,
    match_date,
    home_team,
    away_team,

    -- Goals & Game State
    home_goals,
    away_goals,
    full_time_result,
    ht_home_goals,
    ht_away_goals,
    ht_result,
    ht2_home_goals,
    ht2_away_goals,

    -- Expected Goals (Prioritize Belkat native xG; fallback to Shot Proxy)
    COALESCE(native_home_xg, derived_home_xg) AS home_xg,
    COALESCE(native_away_xg, derived_away_xg) AS away_xg,
    ROUND(
        COALESCE(native_home_xg, derived_home_xg) - COALESCE(native_away_xg, derived_away_xg), 
        2
    ) AS xg_diff,
    
    -- Lineage Flags & Proxies
    (native_home_xg IS NOT NULL) AS is_native_xg,
    derived_home_xg,
    derived_away_xg,

    -- Shots & Performance
    home_shots,
    away_shots,
    home_shots_on_target,
    away_shots_on_target,

    -- Set Pieces & Discipline
    home_corners,
    away_corners,
    home_fouls,
    away_fouls,
    home_yellow_cards,
    away_yellow_cards,
    home_red_cards,
    away_red_cards,

    -- Elo & Form
    home_elo,
    away_elo,
    elo_diff,
    home_form_5,
    away_form_5,

    -- Market & Handicap
    odd_home,
    odd_draw,
    odd_away,
    handicap_size,
    handicap_odd_home,
    handicap_odd_away

FROM calculated