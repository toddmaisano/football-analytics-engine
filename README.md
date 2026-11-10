# Premier League Analytics Engine ⚽📊

A full-stack, high-performance football analytics engine and dashboard built to model, analyze, and visualize multi-season Premier League statistical data.

The application utilizes an ELT pipeline (Python → DuckDB → dbt) managed with `uv` and serves interactive tactical analytics via a FastAPI backend coupled with a React + Plotly frontend.

---

## 🏗 Architecture Overview

```
               +-----------------------+
               |  Raw Data Ingestion   |
               | (src/ingestion.py)    |
               +-----------+-----------+
                           |
                           v
               +-----------------------+
               | DuckDB Storage Engine |
               | (football_warehouse)  |
               +-----------+-----------+
                           |
                           v
               +-----------------------+
               |   dbt Data Models     |
               | (Staging/Inter/Marts) |
               +-----------+-----------+
                           |
                           v
         +-----------------------------------+
         |          FastAPI Server           |
         |         (API Endpoints)           |
         +-----------------+-----------------+
                           |
                           v
         +-----------------------------------+
         |    React + Plotly UI Dashboard    |
         +-----------------------------------+
```

- **Ingestion**: Python script (`src/football_project/ingestion.py`) extracts raw match stats, odds, and expected goals (xG) metrics into DuckDB.
- **Transformation (dbt)**: Modular SQL transformation pipeline inside `models/`:
  - `staging`: Normalizes raw column names, data types, and team identifiers.
  - `intermediate`: Computes derived stats and xG metrics (`int_derived_xg.sql`).
  - `marts`: Exposes production-ready analytics tables (`fct_matches`, `fct_team_match_performance`).
- **Backend**: FastAPI executes dynamic DuckDB SQL queries with filtering parameters and returns structured payloads.
- **Frontend**: A sleek, dark-themed Single Page Application (SPA) built with React and Plotly.js for dynamic visualization rendering.

---

## 📊 Core Features & Visualizations

1. **Cross-Era Head-to-Head (H2H) Rivalry Suite**:
   - Match Goal Margin Distribution (histograms)
   - Multi-Decade xG Trajectories across seasons
   - H2H Variance Scatter (xG Advantage vs. Goal Differential)
   - Multi-Dimensional Parallel Coordinates (Possession, Shots, SOT, xG/Shot)
   - Disciplinary Impact Models (Fouls, Yellows, Reds vs. xG Advantage)

2. **Campaign Efficiency & Tactical Style**:
   - **Tactical Quality Quadrant**: xG Difference vs. Actual Goal Difference (under/overperformance detection).
   - **Elo Dynamics & Win Probability**: Pre-match Elo ratings mapped against actual match realization.
   - **Shot Funnel & Selection Efficiency**: Grouped breakdown of Total Shots → Shots on Target → Total xG → **Actual Goals**.
   - **Territorial Control vs. Sterile Possession**: Possession % vs. Box Penetration Efficiency.

3. **Pressure, Resilience & Momentum**:
   - **Halftime Comeback & Resilience Engine**: Second-half comebacks vs. blown leads.
   - **Defensive Workload vs. Chaos Index**: Measure of defensive pressure under strain.
   - **Season Rolling Momentum**: Chronological 5-match rolling average trajectory across match weeks 1–38.

---

## 🛠 File & Directory Structure

```text
football_project/
├── .gitignore                  # Git exclusions (.db, target, .venv)
├── dbt_project.yml             # dbt project definition & configurations
├── packages.yml                # External dbt dependencies (e.g. dbt-utils)
├── main.py                     # Single entry point: FastAPI app + React dashboard UI
├── football_warehouse.db       # Single DuckDB analytical database source of truth
├── models/
│   ├── staging/                # Raw staging SQL models & schema YAMLs
│   ├── intermediate/           # Business logic & calculated xG intermediate models
│   └── marts/                  # Dimension & fact tables (fct_matches, fct_team_match_performance)
└── src/
    └── football_project/
        ├── __init__.py         # Python package initializers
        └── ingestion.py        # Data retrieval and initial raw loading scripts
```

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.10+**
- **[uv](https://github.com/astral-sh/uv)** (Fast Python package installer and resolver)
- **Git**

To install `uv` (if not already installed):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

### 2. Installation

Clone the repository:
```bash
git clone https://github.com/toddmaisano/football-analytics-engine.git
cd football-analytics-engine
```

Create environment and install dependencies using `uv`:
```bash
# Create virtual environment with uv
uv venv

# Activate the environment
source .venv/bin/activate

# Install all project dependencies
uv pip install fastapi uvicorn duckdb pandas dbt-duckdb
```

---

## 🏃 Running the Project

### Step 1: Run Ingestion
Fetch and load raw data into DuckDB using `uv`:
```bash
uv run python src/football_project/ingestion.py
```

### Step 2: Build dbt Models
Transform raw staging models into production fact tables:
```bash
uv run dbt run
```

*(Optional: Run data quality tests)*
```bash
uv run dbt test
```

### Step 3: Start the Web Dashboard
Launch the FastAPI application:
```bash
uv run uvicorn main:app --reload
```

Open your browser and navigate to:
```text
http://127.0.0.1:8000
```

---

## 📝 License
Distributed under the MIT License. See `LICENSE` for details.
