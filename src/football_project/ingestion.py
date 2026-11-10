import os
import logging
import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = "football_warehouse.db"
HF_BASE_URL = "https://huggingface.co/datasets/eatpizzanot/soccer-dataset/resolve/main"

def rebuild_warehouse():
    # 1. Clear out stale database file for a completely fresh build
    if os.path.exists(DB_PATH):
        logger.info(f"Removing existing warehouse file: {DB_PATH}")
        os.remove(DB_PATH)
    
    logger.info("Connecting to fresh DuckDB warehouse...")
    con = duckdb.connect(DB_PATH)
    
    # 2. Enable DuckDB extensions for remote streaming over HTTP
    con.execute("INSTALL httpfs;")
    con.execute("LOAD httpfs;")
    con.execute("CREATE SCHEMA IF NOT EXISTS raw;")

    # 3. Ingest Football-Data.co.uk Premier League Data (2008/09 to Present) via direct CSV Globbing / Union
    logger.info("--> Ingesting EPL seasons from football-data.co.uk (2008/09 – Present)...")
    
    # Generate the football-data season code paths dynamically (e.g., '0809', '0910', ..., '2526')
    codes = [f"{str(y)[-2:]}{str(y+1)[-2:]}" for y in range(2008, 2026)]
    url_list = [f"https://www.football-data.co.uk/mmz4281/{code}/E0.csv" for code in codes]
    
    try:
        con.execute(f"""
            CREATE TABLE raw.epl_historical_matches AS 
            SELECT *, 
                   -- Extract season code from filename or map it
                   REGEXP_EXTRACT(filename, 'mmz4281/([0-9]{{4}})/E0\\.csv', 1) AS season_code
            FROM read_csv(
                {url_list}, 
                union_by_name=true, 
                ignore_errors=true, 
                auto_detect=true
            );
        """)
        row_cnt = con.execute("SELECT COUNT(*) FROM raw.epl_historical_matches;").fetchone()[0]
        logger.info(f"Loaded {row_cnt:,} rows into raw.epl_historical_matches via native DuckDB streaming.")
    except Exception as e:
        logger.warning(f"Failed direct multi-file CSV read for football-data.co.uk: {e}")

    # 4. Ingest Adam Gábor Global Matches & Elo Datasets directly from GitHub
    logger.info("--> Ingesting Adam Gábor global matches and Elo ratings from GitHub...")
    
    gabor_matches_url = "https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data-2000-2025/refs/heads/main/data/Matches.csv"
    try:
        con.execute(f"""
            CREATE TABLE raw.gabor_matches AS 
            SELECT * FROM read_csv_auto('{gabor_matches_url}', ignore_errors=true);
        """)
        g_matches_cnt = con.execute("SELECT COUNT(*) FROM raw.gabor_matches;").fetchone()[0]
        logger.info(f"Loaded {g_matches_cnt:,} rows into raw.gabor_matches.")
    except Exception as e:
        logger.warning(f"Failed streaming Gábor matches: {e}")

    gabor_elo_url = "https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data-2000-2025/refs/heads/main/data/EloRatings.csv"
    try:
        con.execute(f"""
            CREATE TABLE raw.gabor_elo AS 
            SELECT * FROM read_csv_auto('{gabor_elo_url}', ignore_errors=true);
        """)
        g_elo_cnt = con.execute("SELECT COUNT(*) FROM raw.gabor_elo;").fetchone()[0]
        logger.info(f"Loaded {g_elo_cnt:,} rows into raw.gabor_elo.")
    except Exception as e:
        logger.warning(f"Failed streaming Gábor Elo dataset: {e}")

    # 5. Ingest Hugging Face Parquet Soccer Dataset (Premier League Slice: league_id = 8)
    logger.info("--> Ingesting Premier League slice from Hugging Face Parquet Dataset...")
    try:
        con.execute(f"""
            CREATE TABLE raw.hf_epl_fixtures AS 
            SELECT * FROM read_parquet('{HF_BASE_URL}/fixtures.parquet')
            WHERE league_id = 8;
        """)
        
        con.execute(f"""
            CREATE TABLE raw.hf_epl_teams AS 
            SELECT DISTINCT * FROM read_parquet('{HF_BASE_URL}/teams.parquet');
        """)

        con.execute(f"""
            CREATE TABLE raw.hf_epl_match_stats AS 
            SELECT ms.* FROM read_parquet('{HF_BASE_URL}/match_stats.parquet') ms
            WHERE ms.fixture_id IN (SELECT id FROM raw.hf_epl_fixtures);
        """)

        con.execute(f"""
            CREATE TABLE raw.hf_epl_xg AS 
            SELECT xg.* FROM read_parquet('{HF_BASE_URL}/xg_training.parquet') xg
            WHERE xg.fixture_id IN (SELECT id FROM raw.hf_epl_fixtures);
        """)
        logger.info("Successfully ingested Hugging Face Premier League parquet tables.")
    except Exception as e:
        logger.warning(f"Failed streaming Hugging Face Parquet data: {e}")

# 6. Build the unified core analytical fact table (main.fct_matches) combining records
    logger.info("--> Building unified analytical fact table (main.fct_matches)...")
    
    con.execute("""
        CREATE TABLE main.fct_matches AS
        SELECT 
            CAST(f.id AS VARCHAR) AS fixture_id,
            CAST(f.calendar_year AS VARCHAR) AS season_code,
            CAST(f.date_utc AS TIMESTAMP) AS match_date,
            ht.name AS home_team,
            away_t.name AS away_team,
            CAST(f.goals_home AS INTEGER) AS home_goals,
            CAST(f.goals_away AS INTEGER) AS away_goals,
            CASE 
                WHEN f.goals_home > f.goals_away THEN 'H'
                WHEN f.goals_away > f.goals_home THEN 'A'
                ELSE 'D'
            END AS full_time_result,
            CAST(NULL AS DOUBLE) AS home_xg,
            CAST(NULL AS DOUBLE) AS away_xg,
            CAST(0.0 AS DOUBLE) AS elo_diff
        FROM raw.hf_epl_fixtures f
        LEFT JOIN raw.hf_epl_teams ht ON f.home_team_id = ht.id
        LEFT JOIN raw.hf_epl_teams away_t ON f.away_team_id = away_t.id
        WHERE f.status = 'FT';
    """)

    final_count = con.execute("SELECT COUNT(*) FROM main.fct_matches;").fetchone()[0]
    logger.info(f"Full ingestion pipeline completed successfully! Warehouse built with {final_count:,} core EPL matches.")
    con.close()

if __name__ == "__main__":
    rebuild_warehouse()