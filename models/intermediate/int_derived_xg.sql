WITH epl_matches AS (
    SELECT * FROM {{ ref('stg_epl_matches') }}
),

belkat_stats AS (
    SELECT * FROM {{ ref('stg_belkat_team_stats') }}
)

SELECT
    e.season_code,
    e.match_date,
    e.home_team,
    e.away_team,
    e.home_shots,
    e.home_shots_on_target,
    e.away_shots,
    e.away_shots_on_target,

    -- Shot-Based xG Proxy Calculations
    ROUND(
        (COALESCE(e.home_shots_on_target, 0) * 0.30) + 
        (GREATEST(COALESCE(e.home_shots, 0) - COALESCE(e.home_shots_on_target, 0), 0) * 0.05), 
        2
    ) AS derived_home_xg,

    ROUND(
        (COALESCE(e.away_shots_on_target, 0) * 0.30) + 
        (GREATEST(COALESCE(e.away_shots, 0) - COALESCE(e.away_shots_on_target, 0), 0) * 0.05), 
        2
    ) AS derived_away_xg,

    -- Native Belkat xG (Split by venue join)
    bh.xg_total AS native_home_xg,
    ba.xg_total AS native_away_xg

FROM epl_matches e
LEFT JOIN belkat_stats bh
  ON e.match_date = bh.match_date
 AND bh.venue = 'home'
LEFT JOIN belkat_stats ba
  ON e.match_date = ba.match_date
 AND ba.venue = 'away'