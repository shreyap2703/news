# The Daily Pulse — Global & AI News Dashboard

A small local web app for recent world, India, AI, business, science, and geopolitics headlines.
It has a **React + TypeScript** frontend (Vite) and a small **FastAPI** backend, plus optional user accounts
(log in, sign up, and a profile page) powered by **Supabase**. It was converted from the original single-file
Streamlit app.

## Why React

React fits this app well:

- **Right-sized:** the app is one dashboard view (sidebar filters, topic search, and a story carousel) plus small
  log in, sign-up, and profile pages, and React + Vite (with React Router for the pages) delivers it with very little
  boilerplate.
- **Small and fast:** about 87 KB of gzipped JavaScript to show the headlines, with instant hot reload in
  development. The Supabase client (about 56 KB more) loads separately, and only when accounts are set up.
- **Natural port from Streamlit:** widgets become controlled components, `st.session_state` becomes `useState`, and
  Streamlit's script reruns become React re-renders.
- **Ecosystem:** for example, `react-markdown` safely renders the AI briefing, replacing `st.markdown`.

## Architecture

```text
Browser ── React app (web/) ──/api──▶ FastAPI (api/) ──▶ Google News RSS
                 │                                  └──▶ OpenAI API (optional AI briefing)
                 └────────────────────────────────────▶ Supabase (optional accounts and profiles)
```

The Python data logic from the Streamlit app now runs as a JSON API. A backend is still needed because browsers
cannot read the Google News RSS feed directly (it does not allow cross-origin requests), and it keeps the shared
10-minute cache and backup headlines on the server.

Accounts are optional, and the browser talks to Supabase directly: Supabase Auth handles sign-up, log in, and
sessions, and a `profiles` table stores each user's profile. Row Level Security lets each user read and change only
their own profile, so the FastAPI backend never handles passwords or profile data.

- **Development:** the Vite dev server (port 5173) serves the UI and forwards `/api` requests to FastAPI (port 8000).
- **Production:** `npm run build` writes the UI to `web/dist`, and FastAPI serves it, so one process on port 8000
  hosts both the UI and the API. App pages such as `/login` get the UI's `index.html`, so reloading any page works.

## Project structure

```text
.
├── api/                          FastAPI backend (Python)
│   ├── main.py                   App, routes, and hosting of the built UI (web/dist)
│   ├── news.py                   Google News RSS fetch/parse, 10-minute cache, fallback
│   ├── briefing.py               Optional OpenAI briefing
│   ├── models.py                 Request/response schemas (camelCase JSON)
│   └── fallback_headlines.json   Backup headlines used when the live feed is unavailable
├── supabase/
│   └── migrations/               SQL for the profiles table, its access rules, and the sign-up trigger
├── web/                          React + TypeScript frontend (Vite)
│   ├── .env.example              Template for web/.env.local (Supabase URL and publishable key)
│   ├── src/
│   │   ├── main.tsx              Entry point: router and auth provider
│   │   ├── App.tsx               Navigation bar and page routes
│   │   ├── pages/                NewsPage (headlines dashboard), AuthPage (log in, sign up), ProfilePage
│   │   ├── components/           NavBar, AuthProvider, Sidebar, StoryCarousel, BriefingPanel, Status
│   │   ├── api.ts                Typed client for the /api endpoints
│   │   ├── supabase.ts           Supabase client and profile queries
│   │   ├── auth.ts               Auth context and hook (session and profile state)
│   │   ├── database.types.ts     Types for the Supabase tables
│   │   ├── types.ts              API response types
│   │   └── index.css             Dark theme (ported from the Streamlit custom CSS)
│   └── vite.config.ts            Dev server and /api proxy
└── requirements.txt              Python dependencies
```

## Prerequisites

- Python 3.10 or newer
- Node.js 22.22 or newer (required by React Router)
- Optional: a free [Supabase](https://supabase.com) project, for user accounts

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

## Set up accounts (Supabase)

Headlines work without this step. Until it is done, the **Log in** and **Sign up** pages explain that accounts are
not set up yet. To turn accounts on:

1. Create a free project in the [Supabase dashboard](https://supabase.com/dashboard).
2. Open the project's **SQL Editor**, paste the contents of
   [`supabase/migrations/20261113141500_create_profiles.sql`](supabase/migrations/20261113141500_create_profiles.sql),
   and click **Run**. It creates the `profiles` table, protects it with Row Level Security, and adds a trigger that
   creates a profile for every new user. (With the Supabase CLI, `supabase db push` applies the same file.)
3. In **Authentication → URL Configuration**, set **Site URL** to `http://localhost:5173`, and add
   `http://localhost:5173/**` and `http://localhost:8000/**` to **Redirect URLs**. Confirmation emails link back to
   the app through these addresses.
4. Copy `web/.env.example` to `web/.env.local` (git ignores it) and fill in the project URL and publishable key
   from the project's **Connect** dialog or **Project Settings → API Keys**:

   ```dotenv
   VITE_SUPABASE_URL=https://your-project-ref.supabase.co
   VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
   ```

   The publishable key (or the legacy `anon` key) is designed to be used in browsers: Row Level Security protects
   the data. Never put the secret or `service_role` key in the frontend.
5. Restart `npm run dev`. Vite reads `.env.local` only when it starts.

By default, Supabase asks new users to confirm their email address before they can log in, so sign-up ends with a
"check your email" message. Supabase's built-in email service is rate-limited and meant for testing. For local
development you can turn off **Confirm email** under **Authentication → Sign In / Providers → Email**; for real use,
set up custom SMTP.

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

If you use accounts, create `web/.env.local` before running `npm run build`: Vite writes the Supabase settings into
the bundle at build time, so rebuild after changing them.

## Useful commands

| Where  | Command                                            | Purpose                                                  |
| ------ | -------------------------------------------------- | -------------------------------------------------------- |
| `web/` | `npm run dev`                                      | Dev server with hot reload on port 5173                  |
| `web/` | `npm run build`                                    | Type-check and build the production bundle to `web/dist` |
| `web/` | `npm run lint`                                     | Lint the frontend with Oxlint                            |
| `web/` | `npm run preview`                                  | Preview the production build (also proxies `/api`)       |
| root   | `uvicorn api.main:app --reload --reload-dir api`   | Run the API with auto-reload                             |

## API

Interactive documentation is available at http://localhost:8000/docs while the API is running.

| Method | Path              | Description |
| ------ | ----------------- | ----------- |
| GET    | `/api/categories` | News sections, for example `[{"id": "world", "label": "Top World News"}, ...]`. |
| GET    | `/api/news`       | Headlines for a section. Query: `category` (required), `hours` (1–168, default 24), `limit` (1–50, default 30), `q` (optional search term that replaces the section's default topic), `refresh` (`true` clears the cache). Returns `{category, hours, articles, usingFallback}`. |
| POST   | `/api/briefing`   | Body `{"category", "hours", "limit", "apiKey"}`. Summarizes up to 20 current headlines with `gpt-4.1-mini` using the caller's own key and returns `{"briefing": "<markdown>"}`. |

Accounts do not use this API; the browser calls Supabase directly.

## What it does

- Retrieves recent English headlines and publisher links from the public Google News RSS feed.
- Offers sections for world news, India, IPL cricket, AI/technology, business/economy, science/space, and
  politics/geopolitics.
- Searches any topic with the box above the headlines; choosing another section clears the search.
- Filters by the last 6 hours, 24 hours, or 3 days, and shows 10–50 headlines one story at a time (Previous/Next).
- Caches results for 10 minutes; use **Refresh headlines** to fetch again.
- Shows bundled backup headlines if the live feed is unreachable, and retries the feed after a minute.
- Has a navigation bar on every page with **Log in** and **Sign up**. Accounts are optional: the headlines page is
  the default page and never requires one. After logging in, the bar shows your name, which links to your profile,
  and a **Log out** button.
- Lets you sign up with your name, email address, and password, and keeps you logged in across reloads.
- Stores your profile (name and sign-up date) in Supabase, where you can view and edit it on the profile page.

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
- The info banner, which named GDELT instead of Google News RSS as the source, was removed. The unused GDELT queries
  and title-translation code were dropped because the feed is already English-only.

## Notes

- Google News coverage and ranking vary; this is not a complete feed of every news outlet.
- The UI no longer shows the AI briefing, but the `/api/briefing` endpoint still works. It summarizes headlines only,
  not the full articles, so open the source links and verify important claims. The OpenAI API key is sent only with
  the briefing request and is never stored by this app.
- Supabase Auth stores account passwords (hashed) and issues the session, which the browser keeps in local storage.
  Profiles live in the Supabase `profiles` table, and Row Level Security limits each user to their own row.
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
- **The log in page says "Accounts are not set up yet".** `web/.env.local` is missing or incomplete, or the dev
  server started before you created it. Fill it in (see [Set up accounts](#set-up-accounts-supabase)) and restart
  `npm run dev`; for the production build, run `npm run build` again.
- **Logging in fails with "Email not confirmed".** Open the confirmation link that Supabase emailed you, or turn off
  **Confirm email** for local testing.
- **The confirmation link opens http://localhost:3000 or another wrong address.** Set the **Site URL** and
  **Redirect URLs** in Supabase (step 3 of [Set up accounts](#set-up-accounts-supabase)).
- **Sign-up fails with "Database error saving new user", or the profile page says "The profiles table was not
  found".** The SQL migration has not been run in this Supabase project, or it failed. Run it in the SQL Editor.
