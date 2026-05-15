# AI Carbon & Human ROI Dashboard

An interactive Streamlit dashboard that tells finance and engineering leaders three things at a glance: **how much your AI usage is costing**, **how much CO₂ it's emitting on the current power grid**, and **how that cost compares to the human labor it's replacing**. Built on top of a Snowflake-backed session-log warehouse, with live MISO grid intensity factored in so the carbon math reflects today's fuel mix rather than a static estimate.

![Dashboard screenshot](docs/dashboard.png)

---

## What it shows

- **6 KPI cards** at the top — session count, total carbon (g CO₂), total cost, average user feedback, cost-per-successful-task, live MISO grid intensity (g CO₂/kWh)
- **Model Efficiency Quadrant** — every model placed on a cost-vs-quality scatter with median crosshair, splitting the plane into "high value / low cost" through "low value / high cost" zones
- **Top-15 carbon-emitting models** — horizontal bar with absolute g CO₂ labels and a dynamic title ("X leads carbon emissions — route simple tasks to lighter models")
- **MISO Live Grid Fuel Mix** — current 5-minute fuel breakdown from the MISO Real-Time API, colored by fuel type
- **Cost & Carbon Over Time** — dual-axis line chart with 7-day rolling smoothing, raw values as faint dotted lines underneath
- **Anomaly & Efficiency Flags** — two tabs: 2σ latency anomalies (agent-loop detection) and "Downgrade Candidates" (premium-model sessions with <500-token prompts)
- **HITL ROI Calculator** in the sidebar — adjust tasks/week, AI cost/task, human hourly rate, and minutes/task to get a live "human replaces N× more expensive than AI" multiplier
- **AI Health Summary** — auto-generated plain-English paragraph summarizing the week's highest emitter, best value-per-success model, anomaly count, estimated savings, and whether the grid is cleaner or dirtier than the US average

## Architecture

![Architecture diagram](docs/architecture.png)

The full interactive architecture diagram is on Miro: [view board](https://miro.com/app/board/uXjVHTUX6Ps=/)

Five layers, top to bottom:

| Layer | Components |
|---|---|
| **5 — Deployment** | GitHub repo · Streamlit Cloud · Snowflake key-pair secret |
| **1 — Data Sources** | MISO Real-Time API · Snowflake `AI_API_LOGS` (100K rows) |
| **2 — Python Backend** | `snowflake_connector.py` · `log_parser.py` · `carbon_calculator.py` · `roi_calculator.py` · `anomaly_detector.py` |
| **3 — Output** | Processed DataFrame (cached in Streamlit memory, 5-min TTL) |
| **4 — Streamlit Dashboard** | 7 widgets fed from the processed frame |

## Repository layout

```
.
├── dashboard/
│   └── app.py                 ← Streamlit entry point
├── src/
│   ├── snowflake_connector.py ← Snowflake key-pair auth + local fallback
│   ├── log_parser.py          ← JSONL/CSV reader
│   ├── carbon_calculator.py   ← Token count × MISO grid intensity
│   ├── roi_calculator.py      ← Per-token pricing for 43 models
│   └── anomaly_detector.py    ← Z-score flagging
├── data/
│   ├── raw/
│   │   ├── logs.json          ← 100K-record JSONL fallback dataset
│   │   └── logs.csv           ← Same data, CSV format (for Snowflake upload)
│   └── processed/
│       └── enriched.csv       ← Pipeline output cache
├── docs/
│   ├── dashboard.png          ← Dashboard screenshot
│   └── architecture.png       ← Miro diagram export
├── requirements.txt
└── README.md
```

## Local development

### Prerequisites

- Python 3.10+
- A Snowflake account with the `AI_API_LOGS` table loaded (or use the bundled JSONL fallback — see below)

### 1. Clone and install

```bash
git clone https://github.com/Ajay0704/ai-carbon-roi-dashboard.git
cd ai-carbon-roi-dashboard
pip install -r requirements.txt
```

### 2. Configure Snowflake (optional — falls back to local file)

Generate an RSA keypair and register the public key on your Snowflake user:

```bash
mkdir -p ~/.snowflake
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out ~/.snowflake/snowflake_private_key.p8 -nocrypt
openssl rsa -in ~/.snowflake/snowflake_private_key.p8 -pubout -out ~/.snowflake/snowflake_private_key.pub
```

Copy the public key body (everything between `BEGIN PUBLIC KEY` and `END PUBLIC KEY`, no headers, no newlines) and register it in Snowsight:

```sql
ALTER USER <YOUR_LOGIN_NAME> SET RSA_PUBLIC_KEY='<paste here>';
```

Create a `.env` file in the project root:

```env
SNOWFLAKE_ACCOUNT=your_account_identifier
SNOWFLAKE_USER=YOUR_LOGIN_NAME
SNOWFLAKE_PRIVATE_KEY_PATH=/Users/you/.snowflake/snowflake_private_key.p8
SNOWFLAKE_DATABASE=AI_ROI_DB
SNOWFLAKE_SCHEMA=ANALYTICS
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
SNOWFLAKE_TABLE=AI_API_LOGS
```

`.env` is gitignored — credentials never reach the repo. If Snowflake is unreachable, `load_from_snowflake()` automatically falls back to `data/raw/logs.json` and shows a yellow warning banner in the UI.

### 3. Run

```bash
streamlit run dashboard/app.py
```

The dashboard will open at `http://localhost:8501`. Cold load takes ~5 seconds (Snowflake fetch + carbon/cost enrichment on 100K rows).

## Streamlit Cloud deployment

The dashboard is designed to deploy unmodified to Streamlit Community Cloud. The `snowflake_connector.py` module checks `st.secrets` before falling back to environment variables and the local file path, so the same code works in both environments.

### 1. Push to GitHub

The repo on `main` is deploy-ready — no Cloud-specific changes needed.

### 2. Create a new Streamlit Cloud app

In Streamlit Cloud:

- **Repository:** `Ajay0704/ai-carbon-roi-dashboard`
- **Branch:** `main`
- **Main file path:** `dashboard/app.py`

### 3. Set secrets

Cloud doesn't have a filesystem you can stage `.p8` files to, so the private key goes inline as a TOML triple-quoted string. In the Streamlit Cloud secrets editor (TOML format):

```toml
SNOWFLAKE_ACCOUNT = "your_account_identifier"
SNOWFLAKE_USER = "YOUR_LOGIN_NAME"
SNOWFLAKE_DATABASE = "AI_ROI_DB"
SNOWFLAKE_SCHEMA = "ANALYTICS"
SNOWFLAKE_WAREHOUSE = "COMPUTE_WH"
SNOWFLAKE_TABLE = "AI_API_LOGS"
SNOWFLAKE_PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
<paste the full PEM key body here>
-----END PRIVATE KEY-----"""
```

The connector resolves the key in this order:

1. `SNOWFLAKE_PRIVATE_KEY` as a PEM string (Cloud path)
2. `SNOWFLAKE_PRIVATE_KEY_PATH` as a file path (local dev path)
3. Fall back to `data/raw/logs.json` if neither is set

## Data model

Each session record has 9 fields:

| Field | Type | Notes |
|---|---|---|
| `session_id` | string (UUID) | unique per call (except inside agent-loop bursts) |
| `user_id` | string | `user_NNNN` |
| `model_id` | string | e.g., `gpt-4o`, `claude-3-5-sonnet-20241022` (43 distinct models in the sample data) |
| `prompt_tokens` | int | 200–8000, right-skewed lognormal |
| `completion_tokens` | int | 100–2000, right-skewed lognormal |
| `latency_ms` | int | base + token-driven, with injected anomaly windows |
| `user_feedback_score` | float (1–5) | per-model mean tier (premium ≥ 4.0, mid ~3.3, budget ~2.5) |
| `timestamp` | ISO 8601 | Jan 2024 → Apr 2026, weighted by enterprise adoption curve |
| `cost_usd` | float | pre-computed via the same per-token rates the dashboard uses |

The sample dataset (`data/raw/logs.json`) was generated to reflect public industry usage patterns: ~38% OpenAI flagship (gpt-4o + gpt-4o-mini), ~23% Claude, ~11% Gemini, ~16% open-source models. Weekday/weekend ratio ~2.6×, holiday dips around Dec 20–31 and US Thanksgiving week, mid-2024 enterprise adoption spike around July–September.

## Pricing

Token costs use real published 2024 rates (USD per 1M tokens, split prompt vs completion):

| Model | Prompt | Completion |
|---|---|---|
| `gpt-4o` | $2.50 | $10.00 |
| `claude-3-5-sonnet-20241022` | $3.00 | $15.00 |
| `gemini-1.5-pro` | $1.25 | $5.00 |
| `llama-3-70b` | $0.59 | $0.79 |
| `mistral-large` | $2.00 | $6.00 |
| *all others* | $0.50 | $1.50 |

See `src/roi_calculator.py` to extend.

## Carbon methodology

Carbon emissions per session are computed as:

```
energy_kwh = total_tokens × energy_per_token(model)
carbon_g_co2 = energy_kwh × MISO_grid_intensity_kg_per_kwh × 1000
```

`MISO_grid_intensity` is fetched live every 5 minutes from the [MISO Real-Time Fuel Mix API](https://www.misoenergy.org/) via the [`gridstatus`](https://github.com/gridstatus/gridstatus) library, weighted by lifecycle CO₂ intensity per fuel type (coal 820 g/kWh, natural gas 490, nuclear 12, wind 11, solar 20, etc.). When MISO is unreachable, the dashboard falls back to the US grid average of 386 g CO₂/kWh.

