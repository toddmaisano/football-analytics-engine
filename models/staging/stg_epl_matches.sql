WITH source AS (
    SELECT * FROM raw.epl_historical_matches
)

SELECT
    season_code,
    TRY_CAST("Date" AS DATE) AS match_date,
    CASE 
        WHEN TRIM(HomeTeam) = 'Man City' THEN 'Manchester City'
        WHEN TRIM(HomeTeam) = 'Man United' THEN 'Manchester United'
        WHEN TRIM(HomeTeam) = 'Nott''m Forest' THEN 'Nottingham Forest'
        WHEN TRIM(HomeTeam) = 'Newcastle' THEN 'Newcastle United'
        WHEN TRIM(HomeTeam) = 'Wolves' THEN 'Wolverhampton Wanderers'
        ELSE TRIM(HomeTeam)
    END AS home_team,
    CASE 
        WHEN TRIM(AwayTeam) = 'Man City' THEN 'Manchester City'
        WHEN TRIM(AwayTeam) = 'Man United' THEN 'Manchester United'
        WHEN TRIM(AwayTeam) = 'Nott''m Forest' THEN 'Nottingham Forest'
        WHEN TRIM(AwayTeam) = 'Newcastle' THEN 'Newcastle United'
        WHEN TRIM(AwayTeam) = 'Wolves' THEN 'Wolverhampton Wanderers'
        ELSE TRIM(AwayTeam)
    END AS away_team,
    CAST(FTHG AS INT) AS home_goals,
    CAST(FTAG AS INT) AS away_goals,
    FTR AS full_time_result,
    CAST(HS AS INT) AS home_shots,
    CAST("AS" AS INT) AS away_shots,
    CAST(HST AS INT) AS home_shots_on_target,
    CAST(AST AS INT) AS away_shots_on_target
FROM source