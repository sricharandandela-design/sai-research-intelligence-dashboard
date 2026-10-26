# Sai University Research Intelligence Dashboard

An interactive Streamlit dashboard that retrieves publication records dynamically from the Sai University Publications API.

## Features
- Filter by year, school, SaiU faculty author, document type, indexing status, SJR quartile, publisher and SDG.
- Filter-aware KPIs for total records, Scopus, Web of Science, Q1, schools, faculty authors, SDGs and years.
- Publication trend, school contribution, document type, indexing, quartile, faculty contribution and SDG charts.
- Automatically generated observations, searchable/sortable publication explorer, publication links and CSV export.
- Handles missing metadata without silently removing publication records.

## Run locally
1. Install Python 3.10 or newer.
2. Open a terminal in this folder.
3. Install packages:
   ```bash
   python -m pip install -r requirements.txt
   ```
4. Start the dashboard:
   ```bash
   streamlit run app.py
   ```
5. The app opens in your browser. It fetches live data from:
   `https://sai-publications-dashboard.vercel.app/api/publications`

## Notes on interpretation
- Publication counts are API records after filtering. The app does not deduplicate by title.
- Scopus and WoS counts use the API's `Indexing Status` field. A record can count in both.
- Q1 counts only records explicitly marked `Q1` in `SJR Quartile`.
- Faculty contribution uses `SaiU Authors`, not the full external author list.
- SDG totals count publication-goal associations; one publication may map to multiple goals.
