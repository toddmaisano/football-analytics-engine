WITH source AS (
    SELECT * FROM raw.hf_epl_match_stats
),

unpivoted AS (
    -- Home team perspective
    SELECT
        fixture_id AS match_id,
        TRY_CAST(stats_fetched_at AS DATE) AS match_date,
        'home' AS venue,
        CAST(home_shots_total AS INT) AS shots_total,
        CAST(home_shots_on_goal AS INT) AS shots_on_target,
        CAST(home_xg AS DOUBLE) AS xg_total
    FROM source

    UNION ALL

    -- Away team perspective
    SELECT
        fixture_id AS match_id,
        TRY_CAST(stats_fetched_at AS DATE) AS match_date,
        'away' AS venue,
        CAST(away_shots_total AS INT) AS shots_total,
        CAST(away_shots_on_goal AS INT) AS shots_on_target,
        CAST(away_xg AS DOUBLE) AS xg_total
    FROM source
)

SELECT
    match_id,
    match_date,
    venue,
    shots_total,
    shots_on_target,
    xg_total
FROM unpivoted
WHERE match_date IS NOT NULL