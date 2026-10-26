import re
import requests
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime

API_URL = "https://sai-publications-dashboard.vercel.app/api/publications"

st.set_page_config(
    page_title="Sai University | Research Intelligence",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- Styling ----------
st.markdown("""

<style>
    .stApp {
        background: #f5f7fb;
        color: #172b4d;
    }

    [data-testid="stSidebar"] {
        background: #101a2b;
    }

    [data-testid="stSidebar"] * {
        color: #eef3fb;
    }

    .hero {
        padding: 1.35rem 1.6rem;
        border-radius: 18px;
        background: linear-gradient(115deg, #10213f, #1d4772, #287d91);
        color: #ffffff;
        margin-bottom: 1rem;
    }

    .hero h1 {
        color: #ffffff !important;
        margin: 0 0 .35rem 0;
        font-size: 2rem;
    }

    .hero p {
        color: #dbeafe !important;
        margin: 0;
        font-size: 1rem;
    }

    div[data-testid="stMetric"] {
        background: #ffffff;
        color: #172b4d !important;
        padding: 1rem;
        border-radius: 14px;
        border: 1px solid #e7ebf2;
        box-shadow: 0 3px 14px rgba(16,32,60,.05);
    }

    div[data-testid="stMetric"] label,
    div[data-testid="stMetric"] label *,
    div[data-testid="stMetricValue"],
    div[data-testid="stMetricValue"] *,
    div[data-testid="stMetricDelta"] {
        color: #172b4d !important;
        opacity: 1 !important;
    }

    .section-title {
        color: #14213d !important;
        font-size: 1.15rem;
        font-weight: 700;
        margin: .3rem 0 .65rem;
    }

    .small-note {
        color: #667085 !important;
        font-size: .83rem;
    }

    [data-testid="stCaptionContainer"] {
        color: #667085 !important;
    }
</style>

""", unsafe_allow_html=True)


# ---------- Data loading and cleaning ----------
@st.cache_data(ttl=1800, show_spinner="Fetching the latest publications from Sai University's API…")
def load_data():
    response = requests.get(API_URL, timeout=30)
    response.raise_for_status()
    payload = response.json()
    records = payload.get("data", payload if isinstance(payload, list) else [])
    df = pd.DataFrame(records)
    if df.empty:
        return df

    # Ensure expected columns exist; API values can be missing or blank.
    expected = [
        "Authors", "SaiU Authors", "School", "Title", "Year", "Publication Date",
        "Source title", "Publisher", "Document Type", "Indexing Status",
        "SJR Quartile", "Year Wise Quartile", "DOI", "DOI Link", "Article Link",
        "Journal Link", "Achieved SDG (WoS)", "Achieved SDG (Scopus)", "SaiU SDG Indexing",
        "SaiU Author Email", "Designation", "Abstract", "Keywords", "Scopus URL", "WoS URL"
    ]
    for col in expected:
        if col not in df.columns:
            df[col] = ""

    text_cols = df.select_dtypes(include=["object"]).columns
    for col in text_cols:
        df[col] = df[col].fillna("").astype(str).str.strip()
        df[col] = df[col].replace({"nan": "", "None": "", "NaN": ""})

    # A publication is counted as a record from the API; do not deduplicate by title
    # because separate records/versions may legitimately share titles.
    df["Year_num"] = pd.to_numeric(df["Year"].str.extract(r"(\d{4})", expand=False), errors="coerce").astype("Int64")
    df["Year_label"] = df["Year_num"].astype("string").fillna("Unknown year")
    df["School_clean"] = df["School"].replace("", "Not specified")
    df["Document Type_clean"] = df["Document Type"].replace("", "Not specified")
    df["Publisher_clean"] = df["Publisher"].replace("", "Not specified")
    df["Source_clean"] = df["Source title"].replace("", "Not specified")
    df["Quartile_clean"] = df["SJR Quartile"].str.upper().str.strip().replace("", "Not reported")
    df["Indexing_clean"] = df["Indexing Status"].replace("", "Not reported")

    # Normalize indexing status into flags. Multi-indexed records count in both indexes.
    indexing = df["Indexing Status"].str.lower()
    df["is_scopus"] = indexing.str.contains("scopus", na=False)
    df["is_wos"] = indexing.str.contains(r"\bwos\b|web of science", regex=True, na=False)
    df["is_q1"] = df["SJR Quartile"].str.upper().str.strip().eq("Q1")

    def split_sdg(value):
        if not value:
            return []
        values = re.split(r"[|,;]+", str(value))
        result = []
        for item in values:
            item = item.strip()
            if item.isdigit() and 1 <= int(item) <= 17:
                result.append(int(item))
        return sorted(set(result))

    # Prefer SaiU's combined SDG indexing field for coverage; fall back to WoS/Scopus fields.
    def row_sdgs(row):
        vals = split_sdg(row.get("SaiU SDG Indexing", ""))
        if not vals:
            vals = split_sdg(row.get("Achieved SDG (WoS)", "")) + split_sdg(row.get("Achieved SDG (Scopus)", ""))
        return sorted(set(vals))
    df["SDG_list"] = df.apply(row_sdgs, axis=1)
    df["SDG_count"] = df["SDG_list"].apply(len)
    df["Publication record"] = range(1, len(df) + 1)
    return df

def author_names(value):
    # SaiU Authors reflects the institution's faculty contribution; use it for author KPIs.
    if not value:
        return []
    return [x.strip() for x in re.split(r"[;,|]+", value) if x.strip()]

def make_link(row):
    for col in ["DOI Link", "Article Link", "Journal Link", "Scopus URL", "WoS URL"]:
        value = str(row.get(col, "")).strip()
        if value.startswith("http://") or value.startswith("https://"):
            return value
    doi = str(row.get("DOI", "")).strip()
    return f"https://doi.org/{doi}" if doi else ""

def plot_bar(data, x, y, title, xlabel="", ylabel="Publications", horizontal=False, top_n=None):
    if data.empty:
        st.info("No records match the current filters.")
        return
    chart_data = data.copy()
    if top_n and len(chart_data) > top_n:
        chart_data = chart_data.head(top_n)
    fig, ax = plt.subplots(figsize=(9, 4.2))
    if horizontal:
        sns.barplot(data=chart_data, y=x, x=y, ax=ax)
    else:
        sns.barplot(data=chart_data, x=x, y=y, ax=ax)
        ax.tick_params(axis="x", rotation=35)
    ax.set_title(title, loc="left", fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel(xlabel or (y if horizontal else x))
    ax.set_ylabel(ylabel if horizontal else y)
    sns.despine(ax=ax)
    fig.tight_layout()
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

# ---------- Header ----------
st.markdown("""
<div class="hero">
  <h1>Research Intelligence</h1>
  <p>Sai University · Publication output, quality signals, institutional contributions and SDG coverage</p>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## Explore the research")
    st.caption("Filters update the KPIs, charts and publication explorer.")
    if st.button("↻ Refresh API data", use_container_width=True):
        load_data.clear()
        st.rerun()

try:
    df = load_data()
except Exception as exc:
    st.error("The publications API could not be loaded. Check your internet connection and try again.")
    st.code(str(exc))
    st.stop()

if df.empty:
    st.warning("The API returned no publication records.")
    st.stop()

# ---------- Sidebar filters ----------
with st.sidebar:
    years = sorted([int(x) for x in df["Year_num"].dropna().unique()])
    year_options = st.multiselect("Year", years, default=years)
    school_options = sorted(df["School_clean"].unique().tolist())
    selected_schools = st.multiselect("School", school_options, default=school_options)
    author_pool = sorted({a for value in df["SaiU Authors"] for a in author_names(value)})
    selected_authors = st.multiselect("SaiU faculty author", author_pool)
    doc_options = sorted(df["Document Type_clean"].unique().tolist())
    selected_docs = st.multiselect("Document type", doc_options, default=doc_options)
    index_options = sorted(df["Indexing_clean"].unique().tolist())
    selected_index = st.multiselect("Indexing status", index_options, default=index_options)
    quartile_options = sorted(df["Quartile_clean"].unique().tolist())
    selected_quartiles = st.multiselect("SJR quartile", quartile_options, default=quartile_options)
    publisher_options = sorted(df["Publisher_clean"].unique().tolist())
    selected_publishers = st.multiselect("Publisher", publisher_options, default=publisher_options)
    sdg_options = list(range(1, 18))
    selected_sdgs = st.multiselect("SDG", sdg_options, format_func=lambda n: f"SDG {n}")

filtered = df.copy()
if year_options:
    filtered = filtered[filtered["Year_num"].isin(year_options)]
else:
    filtered = filtered.iloc[0:0]
if selected_schools:
    filtered = filtered[filtered["School_clean"].isin(selected_schools)]
else:
    filtered = filtered.iloc[0:0]
if selected_authors:
    filtered = filtered[filtered["SaiU Authors"].apply(lambda s: any(a in author_names(s) for a in selected_authors))]
if selected_docs:
    filtered = filtered[filtered["Document Type_clean"].isin(selected_docs)]
else:
    filtered = filtered.iloc[0:0]
if selected_index:
    filtered = filtered[filtered["Indexing_clean"].isin(selected_index)]
else:
    filtered = filtered.iloc[0:0]
if selected_quartiles:
    filtered = filtered[filtered["Quartile_clean"].isin(selected_quartiles)]
else:
    filtered = filtered.iloc[0:0]
if selected_publishers:
    filtered = filtered[filtered["Publisher_clean"].isin(selected_publishers)]
else:
    filtered = filtered.iloc[0:0]
if selected_sdgs:
    filtered = filtered[filtered["SDG_list"].apply(lambda vals: any(s in vals for s in selected_sdgs))]
# No SDG selection means no SDG filtering.

# ---------- KPIs ----------
total = len(filtered)
yearly = filtered["Year_num"].dropna()
years_covered = int(yearly.nunique())
schools_count = int(filtered.loc[filtered["School"].ne(""), "School"].nunique())
faculty_count = len({a for value in filtered["SaiU Authors"] for a in author_names(value)})
sdg_count = len({sdg for vals in filtered["SDG_list"] for sdg in vals})
scopus_count = int(filtered["is_scopus"].sum())
wos_count = int(filtered["is_wos"].sum())
q1_count = int(filtered["is_q1"].sum())

st.markdown('<div class="section-title">Research at a glance</div>', unsafe_allow_html=True)



st.markdown("### Research at a glance")

kpis = st.columns(4)

kpis[0].metric("Publications", f"{total:,}")
kpis[1].metric("Scopus", f"{scopus_count:,}")
kpis[2].metric("Web of Science", f"{wos_count:,}")
kpis[3].metric("Q1 Journals", f"{q1_count:,}")

kpis2 = st.columns(4)

kpis2[0].metric("Schools", f"{schools_count:,}")
kpis2[1].metric("Faculty Authors", f"{faculty_count:,}")
kpis2[2].metric("SDGs", f"{sdg_count:,}")
kpis2[3].metric("Years", f"{years_covered:,}")



st.caption(f"Showing {total:,} of {len(df):,} API records · API refresh cache: 30 minutes. Records with missing metadata are retained.")

if total == 0:
    st.warning("No publications match the current filter combination. Adjust or clear one or more filters.")
    st.stop()

# ---------- Insights ----------
st.markdown('<div class="section-title">What the data says</div>', unsafe_allow_html=True)
insights = []
year_counts = filtered.dropna(subset=["Year_num"]).groupby("Year_num").size().sort_index()
if len(year_counts) >= 2:
    first_year, last_year = int(year_counts.index.min()), int(year_counts.index.max())
    first_n, last_n = int(year_counts.iloc[0]), int(year_counts.iloc[-1])
    if first_n:
        change = (last_n - first_n) / first_n * 100
        insights.append(f"Output changed by **{change:+.1f}%** between {first_year} ({first_n}) and {last_year} ({last_n}) in the filtered dataset.")
school_counts = filtered["School_clean"].value_counts()
if len(school_counts):
    insights.append(f"**{school_counts.index[0]}** is the largest contributor in this view, with **{int(school_counts.iloc[0])}** publication records.")
if total:
    indexed_any = filtered["Indexing Status"].str.contains("Scopus|WoS|Web of Science", case=False, regex=True, na=False).sum()
    insights.append(f"**{indexed_any/total*100:.1f}%** of filtered records list Scopus and/or Web of Science indexing.")
sdg_freq = pd.Series([s for vals in filtered["SDG_list"] for s in vals]).value_counts()
if not sdg_freq.empty:
    insights.append(f"**SDG {int(sdg_freq.index[0])}** is the most frequently tagged SDG in this view ({int(sdg_freq.iloc[0])} publication-SDG associations).")
for item in insights:
    st.markdown(f"- {item}")

# ---------- Visualizations ----------
st.markdown('<div class="section-title">Research output and quality</div>', unsafe_allow_html=True)
left, right = st.columns(2)
with left:
    if not year_counts.empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        year_plot = year_counts.reset_index()
        year_plot.columns = ["Year", "Publications"]
        sns.lineplot(data=year_plot, x="Year", y="Publications", marker="o", linewidth=2.5, ax=ax)
        ax.set_title("Publication trend over time", loc="left", fontsize=13, fontweight="bold", pad=12)
        ax.set_xticks(year_plot["Year"].astype(int).tolist())
        ax.tick_params(axis="x", rotation=35)
        sns.despine(ax=ax)
        fig.tight_layout()
        st.pyplot(fig, use_container_width=True)
        plt.close(fig)
with right:
    school_counts_df = filtered["School_clean"].value_counts().head(12).rename_axis("School").reset_index(name="Publications")
    plot_bar(school_counts_df, "School", "Publications", "Publications by school (top 12)", horizontal=True)

left, right = st.columns(2)
with left:
    doc_counts = filtered["Document Type_clean"].value_counts().rename_axis("Document type").reset_index(name="Publications")
    plot_bar(doc_counts, "Document type", "Publications", "Document type mix", horizontal=True, top_n=12)
with right:
    index_counts = filtered["Indexing_clean"].value_counts().rename_axis("Indexing status").reset_index(name="Publications")
    plot_bar(index_counts, "Indexing status", "Publications", "Indexing status distribution", horizontal=True, top_n=10)

left, right = st.columns(2)
with left:
    q_counts = filtered["Quartile_clean"].value_counts().reindex(
        ["Q1", "Q2", "Q3", "Q4", "Not reported"], fill_value=0
    ).rename_axis("SJR quartile").reset_index(name="Publications")
    plot_bar(q_counts, "SJR quartile", "Publications", "SJR quartile distribution")
with right:
    author_counts = {}
    for value in filtered["SaiU Authors"]:
        for author in set(author_names(value)):
            author_counts[author] = author_counts.get(author, 0) + 1
    author_df = pd.DataFrame(sorted(author_counts.items(), key=lambda x: x[1], reverse=True)[:12],
                             columns=["Faculty author", "Publications"])
    plot_bar(author_df, "Faculty author", "Publications", "Top SaiU faculty contributors", horizontal=True)

st.markdown('<div class="section-title">Sustainable Development Goals</div>', unsafe_allow_html=True)
sdg_names = {
    1:"No Poverty", 2:"Zero Hunger", 3:"Good Health and Well-being", 4:"Quality Education",
    5:"Gender Equality", 6:"Clean Water and Sanitation", 7:"Affordable and Clean Energy",
    8:"Decent Work and Economic Growth", 9:"Industry, Innovation and Infrastructure",
    10:"Reduced Inequalities", 11:"Sustainable Cities and Communities", 12:"Responsible Consumption and Production",
    13:"Climate Action", 14:"Life Below Water", 15:"Life on Land", 16:"Peace, Justice and Strong Institutions",
    17:"Partnerships for the Goals"
}
sdg_rows = []
for _, row in filtered.iterrows():
    for sdg in row["SDG_list"]:
        sdg_rows.append({"SDG": f"SDG {sdg}", "Goal": sdg_names.get(sdg, ""), "Publications": row["Publication record"]})
if sdg_rows:
    sdg_df = pd.DataFrame(sdg_rows).groupby(["SDG", "Goal"], as_index=False).agg(Publications=("Publications", "nunique"))
    sdg_df["Goal label"] = sdg_df["SDG"] + " · " + sdg_df["Goal"]
    sdg_df = sdg_df.sort_values("Publications", ascending=False)
    plot_bar(sdg_df, "Goal label", "Publications", "Publications mapped to SDGs", horizontal=True, top_n=17)
    st.caption("A publication may map to multiple SDGs, so SDG counts are associations and can sum to more than the number of publications.")
else:
    st.info("No valid SDG tags are available for the current filter selection.")

# ---------- Publication Explorer ----------
st.markdown('<div class="section-title">Publication explorer</div>', unsafe_allow_html=True)
search = st.text_input("Search titles, authors, schools, sources, DOI or keywords", placeholder="e.g. climate, machine learning, faculty name…")
explorer = filtered.copy()
if search.strip():
    q = search.strip().lower()
    searchable = ["Title", "Authors", "SaiU Authors", "School", "Source title", "Publisher", "DOI", "Keywords", "Abstract"]
    mask = pd.Series(False, index=explorer.index)
    for col in searchable:
        mask |= explorer[col].str.lower().str.contains(re.escape(q), na=False)
    explorer = explorer[mask]

sort_col = st.selectbox("Sort publications by", ["Year (newest)", "Year (oldest)", "Title A–Z", "School A–Z"])
if sort_col == "Year (newest)":
    explorer = explorer.sort_values("Year_num", ascending=False, na_position="last")
elif sort_col == "Year (oldest)":
    explorer = explorer.sort_values("Year_num", ascending=True, na_position="last")
elif sort_col == "Title A–Z":
    explorer = explorer.sort_values("Title", ascending=True)
else:
    explorer = explorer.sort_values("School_clean", ascending=True)

st.caption(f"{len(explorer):,} publication records found.")
display_cols = ["Year", "Title", "SaiU Authors", "School", "Document Type", "Indexing Status", "SJR Quartile", "Source title", "Publisher", "DOI"]
st.dataframe(
    explorer[display_cols].rename(columns={
        "SaiU Authors":"SaiU faculty authors", "Source title":"Source",
        "Document Type":"Document type", "Indexing Status":"Indexing status", "SJR Quartile":"SJR quartile"
    }),
    use_container_width=True, hide_index=True, height=420,
    column_config={
        "Title": st.column_config.TextColumn("Title", width="large"),
        "SaiU faculty authors": st.column_config.TextColumn("SaiU faculty authors", width="medium"),
    }
)

st.markdown("#### Publication details and links")
if len(explorer):
    options = explorer.index.tolist()
    selected_idx = st.selectbox(
        "Choose a publication to inspect",
        options=options,
        format_func=lambda idx: f"{explorer.loc[idx, 'Year'] or 'Year unknown'} · {explorer.loc[idx, 'Title'][:115]}"
    )
    selected = explorer.loc[selected_idx]
    st.markdown(f"### {selected['Title'] or 'Untitled publication'}")
    st.write(f"**Authors:** {selected['Authors'] or 'Not reported'}")
    st.write(f"**SaiU faculty authors:** {selected['SaiU Authors'] or 'Not reported'}")
    st.write(f"**School:** {selected['School'] or 'Not reported'}  ·  **Year:** {selected['Year'] or 'Not reported'}")
    st.write(f"**Source:** {selected['Source title'] or 'Not reported'}  ·  **Publisher:** {selected['Publisher'] or 'Not reported'}")
    st.write(f"**Indexing:** {selected['Indexing Status'] or 'Not reported'}  ·  **SJR quartile:** {selected['SJR Quartile'] or 'Not reported'}")
    if selected["Abstract"]:
        with st.expander("Abstract"):
            st.write(selected["Abstract"])
    links = []
    for label, col in [("DOI", "DOI Link"), ("Article", "Article Link"), ("Journal/source", "Journal Link"),
                       ("Scopus record", "Scopus URL"), ("Web of Science record", "WoS URL")]:
        url = str(selected.get(col, "")).strip()
        if url.startswith("http"):
            links.append((label, url))
    if not links and selected["DOI"]:
        links.append(("DOI", f"https://doi.org/{selected['DOI']}"))
    if links:
        st.markdown(" · ".join([f"[{label}]({url})" for label, url in links]))
    else:
        st.caption("No external publication links are available for this record.")

# ---------- Export ----------
st.markdown('<div class="section-title">Export filtered data</div>', unsafe_allow_html=True)
csv = explorer.drop(columns=["SDG_list"], errors="ignore").to_csv(index=False).encode("utf-8-sig")
st.download_button("Download filtered publications as CSV", data=csv, file_name="sai_research_publications.csv", mime="text/csv")

with st.expander("Data definitions and limitations"):
    st.markdown("""
    - **Publication count:** number of records returned by the API after filtering. Records are not silently deduplicated.
    - **Scopus / Web of Science:** based on the API's `Indexing Status` text. A record indexed in both contributes to both KPI counts.
    - **Q1:** counts records whose `SJR Quartile` field is exactly `Q1`; missing quartiles are not assumed to be Q1.
    - **Faculty authors:** unique names in `SaiU Authors`, which represents Sai University faculty attribution; it is not the same as all co-authors.
    - **SDGs:** parses valid goal numbers (1–17) from `SaiU SDG Indexing`, falling back to the WoS/Scopus SDG fields when that field has no valid numbers. A publication may represent multiple goals.
    - **Missing values:** blank or missing school, publisher, document type, and quartile values are retained and shown as “Not specified” / “Not reported”.
    - **Impact caveat:** indexing and SJR quartile are quality-related metadata, not direct citation or societal-impact measurements.
    """)
st.caption(f"Source: Sai University Publications API · Last fetched by this session: {datetime.now().strftime('%d %b %Y, %H:%M')}")
