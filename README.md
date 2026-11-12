# The Daily Pulse — Global & AI News Dashboard

[![CI](https://github.com/ravichandra-k/news/actions/workflows/ci.yml/badge.svg)](https://github.com/ravichandra-k/news/actions/workflows/ci.yml)

A small local web app for recent world, India, AI, business, science, and geopolitics headlines.
It has a **React + TypeScript** frontend (Vite) and a small **FastAPI** backend. It was converted from the original
single-file Streamlit app.

## Why React

React fits this app well:

- **Right-sized:** the app is one dashboard view (sidebar filters, a story carousel, and an optional AI briefing),
  and React + Vite delivers it with very little boilerplate.
- **Small and fast:** about 107 KB of gzipped JavaScript for the whole app, with instant hot reload in development.
- **Natural port from Streamlit:** widgets become controlled components, `st.session_state` becomes `useState`, and
  Streamlit's script reruns become React re-renders.
- **Ecosystem:** for example, `react-markdown` safely renders the AI briefing, replacing `st.markdown`.

## Architecture

```text
Browser ── React app (web/) ──/api──▶ FastAPI (api/) ──▶ Google News RSS
                                                    └──▶ OpenAI API (optional AI briefing)
```

The Python data logic from the Streamlit app now runs as a JSON API. A backend is still needed because browsers
cannot read the Google News RSS feed directly (it does not allow cross-origin requests), and it keeps the shared
10-minute cache and backup headlines on the server.

- **Development:** the Vite dev server (port 5173) serves the UI and forwards `/api` requests to FastAPI (port 8000).
- **Production:** `npm run build` writes the UI to `web/dist`, and FastAPI serves it, so one process on port 8000
  hosts both the UI and the API.

## Project structure

```text
.
├── .github/workflows/ci.yml      CI: frontend lint and build, backend tests
├── api/                          FastAPI backend (Python)
│   ├── main.py                   App, routes, and hosting of the built UI (web/dist)
│   ├── news.py                   Google News RSS fetch/parse, 10-minute cache, fallback
│   ├── briefing.py               Optional OpenAI briefing
│   ├── models.py                 Request/response schemas (camelCase JSON)
│   └── fallback_headlines.json   Backup headlines used when the live feed is unavailable
├── tests/
│   └── test_api.py               Backend tests (offline: Google News and OpenAI are faked)
├── web/                          React + TypeScript frontend (Vite)
│   ├── src/
│   │   ├── App.tsx               Page layout, data loading, and state
│   │   ├── api.ts                Typed client for the /api endpoints
│   │   ├── types.ts              API response types
│   │   ├── components/           Sidebar, StoryCarousel, BriefingPanel, Status
│   │   └── index.css             Dark theme (ported from the Streamlit custom CSS)
│   └── vite.config.ts            Dev server and /api proxy
├── requirements.txt              Python dependencies
└── requirements-dev.txt          Python dependencies plus test tools (pytest)
```

## Prerequisites

- Python 3.10 or newer
- Node.js 20.19+ or 22.12+ (required by Vite)

## Run it (development)

Terminal 1, the API (start this first):

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
uvicorn api.main:app --reload --reload-dir api --port 8000
```

Terminal 2, the React app:

```bash
cd web
npm install
npm run dev
```

Open http://localhost:5173. UI changes hot-reload, and API changes restart uvicorn automatically. Stop either
server with Ctrl+C.

If `.venv` and `web/node_modules` already exist, skip the setup commands: activate the virtual environment, then run
only `uvicorn ...` and `npm run dev`.

## Run it (production build)

```bash
cd web
npm install
npm run build        # type-checks with tsc and writes web/dist
cd ..
source .venv/bin/activate        # Windows: .venv\Scripts\activate
uvicorn api.main:app --port 8000
```

Open http://localhost:8000. Build the UI before starting the server: FastAPI only serves `web/dist` if it exists at
startup. Add `--host 0.0.0.0` to make it reachable from other devices on your network.

## Useful commands

| Where  | Command                                            | Purpose                                                  |
| ------ | -------------------------------------------------- | -------------------------------------------------------- |
| `web/` | `npm run dev`                                      | Dev server with hot reload on port 5173                  |
| `web/` | `npm run build`                                    | Type-check and build the production bundle to `web/dist` |
| `web/` | `npm run lint`                                     | Lint the frontend with Oxlint                            |
| `web/` | `npm run preview`                                  | Preview the production build (also proxies `/api`)       |
| root   | `uvicorn api.main:app --reload --reload-dir api`   | Run the API with auto-reload                             |
| root   | `python -m pytest`                                 | Run the backend tests (needs `requirements-dev.txt`)     |

## Tests and CI

GitHub Actions runs [`.github/workflows/ci.yml`](.github/workflows/ci.yml) on every push and on pull requests to
`main`. You can also start it manually from the repository's **Actions** tab.

- **Frontend:** `npm ci`, `npm run lint` (Oxlint), and `npm run build` (TypeScript type-check and Vite build) on
  Node.js 24.
- **Backend:** installs `requirements-dev.txt` and runs `python -m pytest` on Python 3.10 and 3.13. The tests in
  `tests/` replace Google News and OpenAI with fakes, so they need no network access or API key.

Run the same checks locally before pushing:

```bash
pip install -r requirements-dev.txt   # in the activated virtual environment
python -m pytest

cd web
npm run lint
npm run build
```

## API

Interactive documentation is available at http://localhost:8000/docs while the API is running.

| Method | Path              | Description |
| ------ | ----------------- | ----------- |
| GET    | `/api/categories` | News sections, for example `[{"id": "world", "label": "Top World News"}, ...]`. |
| GET    | `/api/news`       | Headlines for a section. Query: `category` (required), `hours` (1–168, default 24), `limit` (1–50, default 30), `refresh` (`true` clears the cache). Returns `{category, hours, articles, usingFallback}`. |
| POST   | `/api/briefing`   | Body `{"category", "hours", "limit", "apiKey"}`. Summarizes up to 20 current headlines with `gpt-4.1-mini` using the caller's own key and returns `{"briefing": "<markdown>"}`. |

## What it does

- Retrieves recent English headlines and publisher links from the public Google News RSS feed.
- Offers sections for world news, India, AI/technology, business/economy, science/space, and politics/geopolitics.
- Filters by the last 6 hours, 24 hours, or 3 days, and shows 10–50 headlines one story at a time (Previous/Next).
- Caches results for 10 minutes; use **Refresh headlines** to fetch again.
- Shows bundled backup headlines if the live feed is unreachable, and retries the feed after a minute.
- Can create an optional AI briefing when you enter your own OpenAI API key in the sidebar.

## Changes from the Streamlit version

The Streamlit app (`app.py`) has been replaced. It is still in git history: `git show 96cf9ca:app.py`.

- The UI was rebuilt in React with the same layout, wording, and dark theme. `streamlit` was removed from
  `requirements.txt`.
- The Python data logic moved into the FastAPI `api/` package and is exposed as JSON endpoints.
- **Look back now filters results** (using the Google News `when:` operator). Previously, the selection was ignored
  and stories could be weeks old.
- **Number of headlines is honored up to 50.** It was previously capped at 12.
- Each story links to the original article.
- Google News descriptions only repeat the headline, so stories now show generated context instead. The trailing
  " - Publisher" is removed from titles because the publisher already appears above the title.
- Context keywords match whole words, so headlines containing words such as "said" or "Ukraine" are no longer
  described as AI stories.
- Publication times are shown in your local time zone.
- The info banner now names the real source (Google News RSS, not GDELT). The unused GDELT queries and
  title-translation code were dropped because the feed is already English-only.

## Notes

- Google News coverage and ranking vary; this is not a complete feed of every news outlet.
- The AI briefing summarizes headlines only, not the full articles. Open the source links and verify important claims.
- The OpenAI API key is entered at runtime, sent only with the briefing request, and never stored by this app.
- This project runs locally. Public hosting requires deploying it to a hosting provider and configuring any required
  secrets there.

## Troubleshooting

- **"The news API is unavailable … Make sure the backend server is running."** The React app cannot reach FastAPI.
  Start the API (see above), then click **Refresh headlines**; you do not need to reload the page.
- **`python api/main.py` fails with "attempted relative import with no known parent package".** The API is a
  package and must be started with `uvicorn api.main:app` from the project root.
- **http://127.0.0.1:5173 does not load.** Vite listens on `localhost`, which can resolve to IPv6 only. Use
  http://localhost:5173, or start it with `npm run dev -- --host 127.0.0.1`.
- **The app always shows backup headlines.** The backend cannot reach Google News. On a corporate network with TLS
  inspection, Python may not trust the proxy's certificate: set `REQUESTS_CA_BUNDLE` (Google News) and
  `SSL_CERT_FILE` (OpenAI) to your corporate CA bundle before starting uvicorn.
- **uvicorn reports "Address already in use".** Another process is using port 8000. Stop it, or start the API with
  another `--port` and update the proxy target in `web/vite.config.ts` to match. (Vite automatically moves to the next
  free port if 5173 is taken and prints the URL to open.)
- **`git push` is rejected with "refusing to allow a Personal Access Token to create or update workflow".** Your
  token is not allowed to change files in `.github/workflows/`. Edit the token on GitHub to add **Workflows: Read and
  write** (fine-grained token) or the `workflow` scope (classic token), then push again.
