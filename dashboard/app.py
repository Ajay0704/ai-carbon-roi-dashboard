import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

from log_parser import save_processed
from snowflake_connector import load_from_snowflake
from carbon_calculator import add_carbon_columns, get_miso_fuel_mix
from roi_calculator import add_roi_columns
from anomaly_detector import flag_anomalies

PROCESSED_CSV = Path(__file__).parent.parent / "data" / "processed" / "enriched.csv"

# ── Color system ────────────────────────────────────────────────────────────
PRIMARY = "#1B4F72"
SECONDARY = "#2E86C1"
ACCENT = "#F39C12"
SUCCESS = "#1E8449"
DANGER = "#C0392B"
BG_CARD = "#F8F9FA"
BORDER = "#D5D8DC"
GRIDLINE = "#EAECEE"
TEXT_MUTED = "#7F8C8D"
CHART_COLORS = ["#1B4F72", "#2E86C1", "#F39C12", "#1E8449", "#C0392B", "#8E44AD"]

FUEL_COLORS = {
    "Wind": "#1E8449",
    "Solar": "#F39C12",
    "Nuclear": "#8E44AD",
    "Coal": "#7F8C8D",
    "Natural Gas": "#2E86C1",
    "Other": "#BDC3C7",
    "Battery Storage": "#16A085",
    "Imports": "#D5D8DC",
}

DEFAULT_MODELS = [
    "gpt-4o",
    "claude-3-5-sonnet-20241022",
    "gemini-1.5-pro",
    "llama-3-70b",
    "mistral-large",
]

DOWNGRADE_TARGETS = {"gpt-4-turbo", "claude-3-opus-20240229", "o1-preview"}

st.set_page_config(
    page_title="AI Carbon & Human ROI Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    f"""
    <style>
      .stApp {{ background: #FFFFFF; }}
      .block-container {{ padding-top: 1rem; padding-bottom: 0.5rem; max-width: 100%; }}
      [data-testid="stVerticalBlock"] {{ gap: 0.4rem; }}
      h3 {{ font-size: 0.95rem !important; margin: 0.35rem 0 0.15rem !important;
            color: {PRIMARY}; font-weight: 600; }}
      .footnote {{ color: {TEXT_MUTED}; font-size: 11px; margin: -0.25rem 0 0.5rem 0; }}
      .roi-headline {{ font-size: 2.4rem; font-weight: 800; color: {PRIMARY};
                        text-align: center; line-height: 1; margin: 0.25rem 0; }}
      .roi-sub {{ font-size: 0.7rem; color: {TEXT_MUTED}; text-align: center; }}
      [data-testid="stSidebar"] {{ background: #FAFBFD; }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    "<h1 style='text-align: center; color: #1B4F72; padding-bottom: 0.5rem;'>"
    "AI Carbon & Human ROI Dashboard</h1>",
    unsafe_allow_html=True,
)


def kpi_card(label: str, value: str) -> str:
    return (
        f"<div style='background:#FFFFFF; border-bottom:3px solid {PRIMARY}; "
        f"padding:12px 8px; box-sizing:border-box;'>"
        f"<div style='color:{TEXT_MUTED}; font-size:11px; font-weight:500; "
        f"text-transform:uppercase; letter-spacing:0.05em; "
        f"white-space:nowrap; overflow:hidden; text-overflow:ellipsis;'>{label}</div>"
        f"<div style='color:{PRIMARY}; font-size:24px; font-weight:700; "
        f"line-height:1.2; margin-top:4px; white-space:nowrap; "
        f"overflow:hidden; text-overflow:ellipsis;'>{value}</div>"
        f"</div>"
    )


def footnote(text: str) -> None:
    st.markdown(f"<div class='footnote'>{text}</div>", unsafe_allow_html=True)


def chart_title(text: str) -> None:
    st.markdown(
        f"<p style='font-size:12px; font-weight:600; color:#1B4F72; "
        f"text-align:center; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; "
        f"margin-top:8px; margin-bottom:6px;'>{text}</p>",
        unsafe_allow_html=True,
    )


def row_spacer() -> None:
    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)


def style_fig(fig, height=300, showlegend=False):
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        showlegend=showlegend,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(color="#2C3E50", size=11),
        xaxis=dict(gridcolor=GRIDLINE, zerolinecolor=GRIDLINE, linecolor=BORDER),
        yaxis=dict(gridcolor=GRIDLINE, zerolinecolor=GRIDLINE, linecolor=BORDER),
    )
    return fig


@st.cache_data(ttl=300)
def fetch_miso():
    return get_miso_fuel_mix()


@st.cache_data(show_spinner="Loading session logs…")
def load_and_enrich(grid_intensity_kg_per_kwh: float):
    df = load_from_snowflake()
    df = add_carbon_columns(df, grid_intensity_kg_per_kwh)
    df = add_roi_columns(df)
    df = flag_anomalies(df)
    save_processed(df, PROCESSED_CSV)
    return df


fuel_mix_df, grid_intensity = fetch_miso()
df = load_and_enrich(grid_intensity)

# ── Sidebar ─────────────────────────────────────────────────────────────────
st.sidebar.header("Filters")
all_models = sorted(df["model_id"].unique())
default_selection = [m for m in DEFAULT_MODELS if m in all_models]
models = st.sidebar.multiselect("Model", all_models, default=default_selection)
date_range = st.sidebar.date_input(
    "Date range",
    [df["timestamp"].min().date(), df["timestamp"].max().date()],
)
if len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date = end_date = date_range[0]

st.sidebar.divider()
st.sidebar.header("HITL ROI Calculator")
task_type = st.sidebar.selectbox(
    "Task type",
    ["Document Summary", "Data Extraction", "Email Drafting", "Classification"],
)
tasks_per_week = st.sidebar.number_input("Tasks per week", min_value=1, value=50, step=10)
ai_cost = st.sidebar.number_input("AI cost per task ($)", min_value=0.01, value=2.00, step=0.25, format="%.2f")
human_rate = st.sidebar.number_input("Human hourly rate ($)", min_value=1, value=65, step=5)
human_mins = st.sidebar.number_input("Human minutes per task", min_value=1, value=30, step=5)

human_cost_total = (human_rate / 60) * human_mins * tasks_per_week
ai_cost_total = ai_cost * tasks_per_week
roi = human_cost_total / ai_cost_total if ai_cost_total > 0 else 0

st.sidebar.markdown(f"<div class='roi-headline'>{roi:.1f}×</div>", unsafe_allow_html=True)
st.sidebar.markdown(
    f"<div class='roi-sub'>Human ${human_cost_total:,.0f}/wk → AI ${ai_cost_total:,.0f}/wk<br>{task_type}</div>",
    unsafe_allow_html=True,
)
st.sidebar.markdown(
    f"<div class='footnote' style='margin-top:0.5rem;'>"
    "ROI = (Human $/hr ÷ 60 × min/task × weekly volume) ÷ (AI cost/task × weekly volume)"
    "</div>",
    unsafe_allow_html=True,
)

# ── Filtered data ───────────────────────────────────────────────────────────
mask = (
    df["model_id"].isin(models)
    & (df["timestamp"].dt.date >= start_date)
    & (df["timestamp"].dt.date <= end_date)
)
fdf = df[mask]

# ── Row 1: KPI cards ────────────────────────────────────────────────────────
successful = fdf[fdf["user_feedback_score"] >= 4]
cost_per_success = (fdf["cost_usd"].sum() / len(successful)) if len(successful) else 0

k1, k2, k3, k4, k5, k6 = st.columns([1, 1, 1, 1, 1, 1])
k1.markdown(kpi_card("Sessions", f"{len(fdf):,}"), unsafe_allow_html=True)
k2.markdown(kpi_card("Carbon (g CO₂)", f"{fdf['carbon_g_co2'].sum():,.0f}"), unsafe_allow_html=True)
k3.markdown(kpi_card("Total Cost", f"${fdf['cost_usd'].sum():,.2f}"), unsafe_allow_html=True)
k4.markdown(kpi_card("Avg Feedback", f"{fdf['user_feedback_score'].mean():.2f}" if len(fdf) else "—"), unsafe_allow_html=True)
k5.markdown(kpi_card("Cost / Success", f"${cost_per_success:.3f}"), unsafe_allow_html=True)
k6.markdown(kpi_card("Grid Intensity", f"{grid_intensity * 1000:.0f} g/kWh"), unsafe_allow_html=True)

st.markdown("<hr style='border: none; border-top: 1px solid #EAECEE; margin: 8px 0 16px 0;'>", unsafe_allow_html=True)

# ── Row 2: MISO fuel mix bar ────────────────────────────────────────────────
chart_title("MISO Live Grid Fuel Mix")
if fuel_mix_df["MW"].sum() > 0:
    sorted_fuel = fuel_mix_df.sort_values("MW", ascending=False)
    bar_colors = [FUEL_COLORS.get(f, TEXT_MUTED) for f in sorted_fuel["Fuel"]]
    fig_fuel = go.Figure()
    fig_fuel.add_trace(go.Bar(
        x=sorted_fuel["Fuel"], y=sorted_fuel["MW"],
        marker_color=bar_colors,
        text=sorted_fuel["Pct"].apply(lambda p: f"{p:.1f}%"),
        textposition="outside",
        textfont=dict(size=11, color=PRIMARY),
        hovertemplate="<b>%{x}</b><br>%{y:,.0f} MW<extra></extra>",
    ))
    style_fig(fig_fuel, height=180)
    fig_fuel.update_layout(
        title="",
        xaxis=dict(showgrid=False, linecolor=BORDER),
        yaxis=dict(nticks=3, gridcolor=GRIDLINE, linecolor=BORDER, title=None),
    )
    st.plotly_chart(fig_fuel, use_container_width=True)
else:
    st.info("MISO fuel mix unavailable — using fallback US-average intensity.")
footnote("Source: MISO Real-Time Fuel Mix API — refreshes every 5 minutes")
row_spacer()

# ── Row 3: Model Efficiency Quadrant | Carbon Top 15 ────────────────────────
r3c1, r3c2 = st.columns(2)

with r3c1:
    chart_title("Premium models cost more but score higher")
    if len(fdf) > 0:
        per_model = (
            fdf.groupby("model_id")
            .agg(avg_cost=("cost_usd", "mean"),
                 avg_feedback=("user_feedback_score", "mean"),
                 n=("session_id", "count"))
            .reset_index()
        )
        median_cost = per_model["avg_cost"].median()
        median_fb = per_model["avg_feedback"].median()
        x_max = per_model["avg_cost"].max() * 1.05
        y_max = 5.0
        y_min = max(per_model["avg_feedback"].min() - 0.2, 1.0)

        fig_q = go.Figure()
        # Quadrant backgrounds — low alpha tints
        fig_q.add_shape(type="rect", x0=0, x1=median_cost, y0=median_fb, y1=y_max,
                        fillcolor="rgba(30,132,73,0.08)", line_width=0, layer="below")
        fig_q.add_shape(type="rect", x0=median_cost, x1=x_max, y0=median_fb, y1=y_max,
                        fillcolor="rgba(243,156,18,0.08)", line_width=0, layer="below")
        fig_q.add_shape(type="rect", x0=0, x1=median_cost, y0=y_min, y1=median_fb,
                        fillcolor="rgba(243,156,18,0.08)", line_width=0, layer="below")
        fig_q.add_shape(type="rect", x0=median_cost, x1=x_max, y0=y_min, y1=median_fb,
                        fillcolor="rgba(192,57,43,0.08)", line_width=0, layer="below")

        fig_q.add_vline(x=median_cost, line_dash="dot", line_color=ACCENT, line_width=1.2)
        fig_q.add_hline(y=median_fb, line_dash="dot", line_color=ACCENT, line_width=1.2)

        annotations = [
            dict(x=median_cost / 2, y=y_max - 0.05, text="<b>High Value · Low Cost</b>",
                 showarrow=False, font=dict(size=10, color=SUCCESS), xanchor="center"),
            dict(x=(median_cost + x_max) / 2, y=y_max - 0.05, text="<b>High Value · High Cost</b>",
                 showarrow=False, font=dict(size=10, color=ACCENT), xanchor="center"),
            dict(x=median_cost / 2, y=y_min + 0.05, text="<b>Low Value · Low Cost</b>",
                 showarrow=False, font=dict(size=10, color=ACCENT), xanchor="center"),
            dict(x=(median_cost + x_max) / 2, y=y_min + 0.05, text="<b>Low Value · High Cost</b>",
                 showarrow=False, font=dict(size=10, color=DANGER), xanchor="center"),
        ]

        fig_q.add_trace(go.Scatter(
            x=per_model["avg_cost"], y=per_model["avg_feedback"],
            mode="markers+text",
            marker=dict(
                size=(per_model["n"] / per_model["n"].max() * 26 + 6),
                color=PRIMARY, opacity=0.78,
                line=dict(color="white", width=1.2),
            ),
            text=per_model["model_id"].str.replace("-20241022", "")
                                       .str.replace("-20240229", "")
                                       .str.replace("-20240307", ""),
            textposition="top center",
            textfont=dict(size=8, color="#2C3E50"),
            hovertemplate="<b>%{customdata[0]}</b><br>Avg cost: $%{x:.4f}<br>"
                          "Avg feedback: %{y:.2f}<br>Sessions: %{customdata[1]:,}<extra></extra>",
            customdata=per_model[["model_id", "n"]].values,
            showlegend=False,
        ))

        style_fig(fig_q, height=320)
        fig_q.update_layout(
            annotations=annotations,
            xaxis_title="Avg Cost per Session (USD)",
            yaxis_title="Avg Feedback Score",
            xaxis=dict(range=[0, x_max], gridcolor=GRIDLINE, linecolor=BORDER),
            yaxis=dict(range=[y_min, y_max], gridcolor=GRIDLINE, linecolor=BORDER),
        )
        st.plotly_chart(fig_q, use_container_width=True)
    else:
        st.info("No data in current filter.")

with r3c2:
    if len(fdf) > 0:
        carbon_by_model = fdf.groupby("model_id")["carbon_g_co2"].sum().sort_values(ascending=False)
        top_emitter = carbon_by_model.index[0]
        top_models = (
            carbon_by_model.head(15)
            .reset_index()
            .sort_values("carbon_g_co2", ascending=True)  # plotly h-bar bottom-up
        )
        chart_title(
            f"{top_emitter} leads carbon emissions — route simple tasks to lighter models"
        )
        fig_top = go.Figure()
        fig_top.add_trace(go.Bar(
            x=top_models["carbon_g_co2"], y=top_models["model_id"],
            orientation="h",
            marker=dict(color=top_models["carbon_g_co2"], colorscale=[[0, SECONDARY], [1, PRIMARY]]),
            text=top_models["carbon_g_co2"].apply(lambda v: f"{v:,.0f} g"),
            textposition="outside",
            textfont=dict(size=10, color=PRIMARY),
            hovertemplate="<b>%{y}</b><br>%{x:,.0f} g CO₂<extra></extra>",
        ))
        style_fig(fig_top, height=320)
        fig_top.update_layout(
            xaxis_title="g CO₂",
            yaxis_title=None,
            xaxis=dict(gridcolor=GRIDLINE, linecolor=BORDER),
            yaxis=dict(gridcolor=GRIDLINE, linecolor=BORDER),
        )
        st.plotly_chart(fig_top, use_container_width=True)
    else:
        st.markdown("### Carbon Emissions — Top 15 Models")
        st.info("No data in current filter.")

footnote("Carbon methodology: token count × model energy estimate × live MISO grid intensity")
row_spacer()

# ── Row 4: Cost & Carbon Over Time | Anomaly Flags ──────────────────────────
r4c1, r4c2 = st.columns(2)

with r4c1:
    chart_title("Cost is stable · Carbon follows grid mix")
    daily = (
        fdf.set_index("timestamp")
        .resample("D")
        .agg(cost_usd=("cost_usd", "sum"), carbon_g_co2=("carbon_g_co2", "sum"))
        .reset_index()
    )
    daily["cost_smooth"] = daily["cost_usd"].rolling(7, min_periods=1).mean()
    daily["carbon_smooth"] = daily["carbon_g_co2"].rolling(7, min_periods=1).mean()

    fig_cc = make_subplots(specs=[[{"secondary_y": True}]])
    # Raw faint dotted (cost)
    fig_cc.add_trace(
        go.Scatter(x=daily["timestamp"], y=daily["cost_usd"],
                   name="Cost (raw)",
                   line=dict(color=PRIMARY, width=1, dash="dot"),
                   opacity=0.2, showlegend=False),
        secondary_y=False,
    )
    # Smooth solid (cost)
    fig_cc.add_trace(
        go.Scatter(x=daily["timestamp"], y=daily["cost_smooth"],
                   name="Cost (7-day avg)",
                   line=dict(color=PRIMARY, width=2.2)),
        secondary_y=False,
    )
    # Raw faint dotted (carbon)
    fig_cc.add_trace(
        go.Scatter(x=daily["timestamp"], y=daily["carbon_g_co2"],
                   name="Carbon (raw)",
                   line=dict(color=SUCCESS, width=1, dash="dot"),
                   opacity=0.2, showlegend=False),
        secondary_y=True,
    )
    # Smooth solid (carbon)
    fig_cc.add_trace(
        go.Scatter(x=daily["timestamp"], y=daily["carbon_smooth"],
                   name="Carbon (7-day avg)",
                   line=dict(color=SUCCESS, width=2.2)),
        secondary_y=True,
    )
    style_fig(fig_cc, height=300, showlegend=True)
    fig_cc.update_yaxes(title_text="USD/day", secondary_y=False, gridcolor=GRIDLINE, linecolor=BORDER)
    fig_cc.update_yaxes(title_text="g CO₂/day", secondary_y=True, showgrid=False, linecolor=BORDER)
    fig_cc.update_layout(
        xaxis_title=None,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    font=dict(size=10, color=TEXT_MUTED)),
    )
    st.plotly_chart(fig_cc, use_container_width=True)
    footnote("Carbon methodology: token count × model energy estimate × live MISO grid intensity")

with r4c2:
    chart_title("Recoverable waste: loops & over-provisioned tasks")

    tab_latency, tab_downgrade = st.tabs(["Latency anomalies", "Downgrade candidates"])

    with tab_latency:
        if len(fdf) > 0:
            lat_mean = fdf["latency_ms"].mean()
            lat_std = fdf["latency_ms"].std()
            threshold = lat_mean + 2 * lat_std
            flags = fdf[fdf["latency_ms"] > threshold].copy()
            flags["flag_reason"] = (
                ((flags["latency_ms"] - lat_mean) / lat_std).round(1).astype(str) + "σ latency"
            )
            st.markdown(
                f"<div class='footnote' style='margin:0 0 0.25rem 0;'>"
                f"{len(flags):,} flagged · threshold {threshold:,.0f} ms · mean {lat_mean:,.0f} ms"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.dataframe(
                flags[["session_id", "model_id", "latency_ms", "prompt_tokens",
                       "user_feedback_score", "flag_reason"]]
                .sort_values("latency_ms", ascending=False)
                .head(200),
                height=230, use_container_width=True, hide_index=True,
            )
        else:
            st.info("No data in current filter.")

    with tab_downgrade:
        downgrade = fdf[
            fdf["model_id"].isin(DOWNGRADE_TARGETS)
            & (fdf["prompt_tokens"] < 500)
        ].copy()
        downgrade["flag_reason"] = "Downgrade Candidate — consider cheaper model"
        st.markdown(
            f"<div class='footnote' style='margin:0 0 0.25rem 0;'>"
            f"{len(downgrade):,} sessions on premium models with prompt_tokens < 500"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.dataframe(
            downgrade[["session_id", "model_id", "prompt_tokens", "cost_usd",
                       "user_feedback_score", "flag_reason"]]
            .sort_values("cost_usd", ascending=False)
            .head(200),
            height=230, use_container_width=True, hide_index=True,
        )

row_spacer()

# ── AI Health Summary (collapsible, bottom of page) ─────────────────────────
with st.expander("AI Health Summary", expanded=True):
    if len(fdf) > 0:
        carbon_by_model = fdf.groupby("model_id")["carbon_g_co2"].sum()
        top_carbon_model = carbon_by_model.idxmax()
        top_carbon_value = carbon_by_model.max()

        per_model = fdf.groupby("model_id").agg(
            total_cost=("cost_usd", "sum"),
            successes=("user_feedback_score", lambda s: (s >= 4).sum()),
        )
        per_model = per_model[per_model["successes"] > 0]
        if len(per_model):
            per_model["cost_per_success"] = per_model["total_cost"] / per_model["successes"]
            best_value_model = per_model["cost_per_success"].idxmin()
            best_value_amount = per_model["cost_per_success"].min()
        else:
            best_value_model = "no model"
            best_value_amount = 0.0

        lat_mean = fdf["latency_ms"].mean()
        lat_std = fdf["latency_ms"].std()
        anomaly_count = int((fdf["latency_ms"] > lat_mean + 2 * lat_std).sum())
        avg_cost_per_session = float(fdf["cost_usd"].mean())
        savings_estimate = anomaly_count * avg_cost_per_session * 50

        miso_g = grid_intensity * 1000
        us_avg = 386.0
        delta_pct = (us_avg - miso_g) / us_avg * 100
        if delta_pct > 0:
            grid_phrase = f"{delta_pct:.0f}% cleaner than the US average"
        elif delta_pct < 0:
            grid_phrase = f"{abs(delta_pct):.0f}% dirtier than the US average"
        else:
            grid_phrase = "running at the US average"

        st.markdown(
            f"This week **{top_carbon_model}** was your highest carbon emitter at "
            f"**{top_carbon_value:,.0f} g CO₂**. **{best_value_model}** had the best "
            f"cost-per-success ratio at **\\${best_value_amount:.3f}**. "
            f"**{anomaly_count} agent loop anomalies** were detected, preventing an estimated "
            f"**\\${savings_estimate:,.2f}** in wasted spend. The MISO grid is currently "
            f"**{grid_phrase}** ({miso_g:.0f} vs 386 g CO₂/kWh)."
        )
    else:
        st.info("No sessions in current filter — adjust models or date range to see the summary.")
