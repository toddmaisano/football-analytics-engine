WITH source AS (
    SELECT
        CAST(date AS DATE) AS rating_date,
        CASE 
            WHEN TRIM(club) = 'Man City' THEN 'Manchester City'
            WHEN TRIM(club) = 'Man United' THEN 'Manchester United'
            WHEN TRIM(club) = 'Nott''m Forest' THEN 'Nottingham Forest'
            WHEN TRIM(club) = 'Newcastle' THEN 'Newcastle United'
            WHEN TRIM(club) = 'Wolves' THEN 'Wolverhampton Wanderers'
            ELSE TRIM(club)
        END AS team_name,
        country,
        CAST(elo AS DOUBLE) AS elo_rating,
        ROW_NUMBER() OVER (
            PARTITION BY 
                CAST(date AS DATE), 
                TRIM(club)
            ORDER BY date DESC
        ) AS dedup_idx
    FROM {{ source('raw', 'gabor_elo') }}
    WHERE date IS NOT NULL AND club IS NOT NULL
)

SELECT
    rating_date,
    team_name,
    country,
    elo_rating
FROM source
WHERE dedup_idx = 1