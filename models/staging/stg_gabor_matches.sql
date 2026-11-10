WITH source AS (
    SELECT
        Division AS division,
        CAST(MatchDate AS DATE) AS match_date,
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
        CAST(FTHome AS INT) AS home_goals,
        CAST(FTAway AS INT) AS away_goals,
        FTResult AS full_time_result,
        CAST(HTHome AS INT) AS ht_home_goals,
        CAST(HTAway AS INT) AS ht_away_goals,
        HTResult AS ht_result,
        CAST(HomeElo AS DOUBLE) AS home_elo,
        CAST(AwayElo AS DOUBLE) AS away_elo,
        CAST(Form3Home AS DOUBLE) AS home_form_3,
        CAST(Form5Home AS DOUBLE) AS home_form_5,
        CAST(Form3Away AS DOUBLE) AS away_form_3,
        CAST(Form5Away AS DOUBLE) AS away_form_5,
        CAST(HomeShots AS INT) AS home_shots,
        CAST(AwayShots AS INT) AS away_shots,
        CAST(HomeTarget AS INT) AS home_shots_on_target,
        CAST(AwayTarget AS INT) AS away_shots_on_target,
        CAST(HomeFouls AS INT) AS home_fouls,
        CAST(AwayFouls AS INT) AS away_fouls,
        CAST(HomeCorners AS INT) AS home_corners,
        CAST(AwayCorners AS INT) AS away_corners,
        CAST(HomeYellow AS INT) AS home_yellow_cards,
        CAST(AwayYellow AS INT) AS away_yellow_cards,
        CAST(HomeRed AS INT) AS home_red_cards,
        CAST(AwayRed AS INT) AS away_red_cards,
        CAST(OddHome AS DOUBLE) AS odd_home,
        CAST(OddDraw AS DOUBLE) AS odd_draw,
        CAST(OddAway AS DOUBLE) AS odd_away,
        CAST(HandiSize AS DOUBLE) AS handicap_size,
        CAST(HandiHome AS DOUBLE) AS handicap_odd_home,
        CAST(HandiAway AS DOUBLE) AS handicap_odd_away,
        ROW_NUMBER() OVER (
            PARTITION BY 
                CAST(MatchDate AS DATE), 
                TRIM(HomeTeam), 
                TRIM(AwayTeam)
            ORDER BY MatchDate
        ) AS dedup_idx
    FROM {{ source('raw', 'gabor_matches') }}
    WHERE MatchDate IS NOT NULL
)

SELECT
    division,
    match_date,
    home_team,
    away_team,
    home_goals,
    away_goals,
    full_time_result,
    ht_home_goals,
    ht_away_goals,
    ht_result,
    home_elo,
    away_elo,
    home_form_3,
    home_form_5,
    away_form_3,
    away_form_5,
    home_shots,
    away_shots,
    home_shots_on_target,
    away_shots_on_target,
    home_fouls,
    away_fouls,
    home_corners,
    away_corners,
    home_yellow_cards,
    away_yellow_cards,
    home_red_cards,
    away_red_cards,
    odd_home,
    odd_draw,
    odd_away,
    handicap_size,
    handicap_odd_home,
    handicap_odd_away
FROM source
WHERE dedup_idx = 1