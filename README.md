# The Daily Pulse — Global & AI News Dashboard

A small local web app for recent world, India, AI, business, science, and geopolitics headlines.

## Run it

1. Install Python 3.10 or newer.
2. Unzip this folder.
3. Open a terminal in this folder and run:

   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # macOS/Linux:
   source .venv/bin/activate

   pip install -r requirements.txt
   streamlit run app.py
   ```

4. Streamlit opens the dashboard in your browser (usually http://localhost:8501).

## What it does

- Retrieves recent article headlines and publisher links through the public GDELT DOC API.
- Offers sections for world news, India, AI/technology, business/economy, science/space, and geopolitics.
- Filters by the last 6 hours, 24 hours, or 3 days.
- Caches results for 10 minutes; use Refresh headlines to fetch again.
- Can create an optional AI briefing when you enter your own OpenAI API key in the sidebar.

## Notes

- GDELT coverage and indexing can vary; this is not a complete feed of every news outlet.
- The AI briefing summarizes headlines only, not the full articles. Open source links and verify important claims.
- The OpenAI API key is entered at runtime and is not stored by this app.
- This package runs locally. Public hosting requires deploying it to a hosting provider and configuring any required secrets there.
