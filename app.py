import streamlit as st
import pandas as pd
import plotly.express as px
from data_fetcher import fetch_real_data
from logic_core import RegistrationTrialExtractor

st.set_page_config(page_title="MediLine Registration Filter", layout="wide", page_icon="💊")
st.markdown("<style>.stMetric { background-color: #f0f2f6; padding: 10px; border-radius: 5px; }</style>", unsafe_allow_html=True)

# Header
st.title("💊 MediLine: Registration Trial Engine (v2.0)")
st.markdown("""
**Logic v2.0**: FDA規制チェックの厳格化、Phase 2 Pivotal (迅速承認候補) の自動検出、主要評価項目による難易度推定をサポート。
""")

# Sidebar
with st.sidebar:
    st.header("⚙️ Search Params")
    search_term = st.text_input("Disease / Condition", value="Non-small cell lung cancer")
    num_trials = st.slider("Fetch Limit", 100, 1000, 20)
    
    if st.button("🔄 Analyze Pipeline"):
        st.cache_data.clear()
    
    st.divider()
    st.markdown("### 🔍 Logic Info")
    st.caption("""
    - **Hard Filter**: Industry Sponsor, No IIT, Phase 2/3.
    - **FDA Check**: Strict (Soft Reject if No).
    - **Context**: Mining Title, Summary, & Detailed Desc.
    - **Priority**: Phase 2 + 'Pivotal'/'Confirmatory'.
    """)

# Data Processing
@st.cache_data
def load_data(n, term):
    raw_df = fetch_real_data(limit=n, query_term=term)
    if raw_df.empty: return pd.DataFrame()
    
    extractor = RegistrationTrialExtractor()
    processed_df = extractor.process(raw_df)
    processed_df['ctg_url'] = "https://clinicaltrials.gov/study/" + processed_df['nct_id']
    return processed_df

# Run
with st.spinner(f"Mining CTG data for '{search_term}'..."):
    df_result = load_data(num_trials, search_term)

if df_result.empty:
    st.warning("No data found.")
    st.stop()

# Segmentation
df_priority = df_result[df_result['ui_status'] == "🔥 Priority"]
df_kept = df_result[df_result['ui_status'] == "✅ Kept"]
df_rejected = df_result[df_result['ui_status'] == "❌ Rejected"]

# Metrics
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Scanned", len(df_result))
col2.metric("🔥 Priority Candidates", len(df_priority))
col3.metric("✅ Qualified", len(df_kept))
col4.metric("❌ Noise / Rejected", len(df_rejected))

st.divider()

# Visualization
c1, c2 = st.columns([1, 2])
with c1:
    st.markdown("### 📊 Rejection Analysis")
    if not df_rejected.empty:
        # 理由を簡略化して集計
        df_rejected['reason_short'] = df_rejected['reject_reason'].apply(lambda x: x.split('(')[0] if '(' in x else x)
        fig = px.pie(df_rejected, names='reason_short', title='Why trials were rejected?', hole=0.4)
        st.plotly_chart(fig, use_container_width=True)

with c2:
    st.markdown("### 🕵️ Pipeline Inspector")
    
    tab1, tab2, tab3 = st.tabs(["🔥 Priority & Qualified", "❌ Rejected Noise", "🔍 Raw Data"])
    
    # 共通カラム設定
    common_cfg = {
        "nct_id": "NCT ID",
        "ctg_url": st.column_config.LinkColumn("Link", display_text="Open 🔗"),
        "intervention_name": "Drug / Intervention",
        "sponsor_name": "Sponsor",
        "phase": "Phase",
        "primary_completion_date": st.column_config.TextColumn("PCD (Launch Est.)", help="Primary Completion Date"),
        "primary_outcomes": st.column_config.TextColumn("Primary Endpoint", width="large"),
        "final_decision": st.column_config.TextColumn("Decision", help="AI Logic Decision")
    }

    with tab1:
        # PriorityとQualifiedを結合して表示（Priorityを上に）
        df_show = pd.concat([df_priority, df_kept])
        if not df_show.empty:
            st.dataframe(
                df_show[['ui_status', 'nct_id', 'ctg_url', 'intervention_name', 'sponsor_name', 'phase', 'primary_completion_date', 'primary_outcomes', 'final_decision']],
                column_config=common_cfg,
                hide_index=True,
                use_container_width=True
            )
        else:
            st.info("No qualified trials found.")

    with tab2:
        st.dataframe(
            df_rejected[['nct_id', 'ctg_url', 'reject_reason', 'sponsor_name', 'official_title']],
            column_config={
                "reject_reason": st.column_config.TextColumn("Reason", width="medium"),
                "ctg_url": st.column_config.LinkColumn("Link", display_text="View")
            },
            hide_index=True,
            use_container_width=True
        )

    with tab3:
        st.dataframe(df_result)