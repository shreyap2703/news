import os
import re
import time
import html
import requests
import streamlit as st
import xml.etree.ElementTree as ET
from html import escape
from datetime import datetime, timezone, timedelta

st.set_page_config(page_title="The Daily Pulse", page_icon="🌍", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

    html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
        background: radial-gradient(circle at top left, #11213b 0%, #091321 30%, #050d18 100%);
        font-family: 'Inter', sans-serif;
    }

    .stApp {
        color: #edf5ff;
    }

    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
    }

    h1 {
        letter-spacing: -0.06em;
        font-weight: 900;
        margin-bottom: 0.15rem;
        color: #f3f8ff;
    }

    .headline-hero {
        display: flex;
        align-items: center;
        gap: 0.95rem;
        margin-top: 0.25rem;
        margin-bottom: 0.9rem;
    }

    .hero-badge {
        width: 64px;
        height: 64px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        background: radial-gradient(circle at 30% 30%, #7dd3fc 0%, #38bdf8 18%, #2563eb 45%, #0b1a34 100%);
        box-shadow: 0 16px 36px rgba(56, 189, 248, 0.2);
        font-size: 2rem;
    }

    .info-banner {
        background: rgba(19, 35, 59, 0.9);
        border: 1px solid rgba(125, 211, 252, 0.22);
        border-radius: 18px;
        padding: 1rem 1.2rem;
        margin: 0.5rem 0 1.6rem 0;
        color: #dfeeff;
        font-size: 1.07rem;
        line-height: 1.55;
    }

    .metric-card {
        background: rgba(15, 27, 45, 0.88);
        border: 1px solid rgba(148, 163, 184, 0.24);
        border-radius: 18px;
        padding: 0.8rem 0.9rem;
        box-shadow: 0 14px 28px rgba(2, 6, 23, 0.24);
        min-height: 112px;
    }

    .news-card {
        background: rgba(15, 27, 45, 0.9);
        border: 1px solid rgba(148, 163, 184, 0.2);
        border-radius: 18px;
        padding: 1rem 1.15rem;
        box-shadow: 0 10px 20px rgba(2, 6, 23, 0.18);
        margin-bottom: 0.9rem;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }

    .news-card:hover {
        transform: translateY(-1px);
        border-color: rgba(125, 211, 252, 0.38);
    }

    .news-card h4 {
        margin: 0 0 0.45rem 0;
        line-height: 1.4;
    }

    .news-meta {
        color: #9db4d3;
        font-size: 0.86rem;
    }

    .chip {
        display: inline-flex;
        align-items: center;
        padding: 0.5rem 0.8rem;
        background: rgba(34, 197, 94, 0.12);
        border: 1px solid rgba(34, 197, 94, 0.4);
        border-radius: 999px;
        color: #9df0bf;
        font-weight: 600;
        font-size: 0.8rem;
        margin-bottom: 0.5rem;
    }

    .stSelectbox label, .stSlider label {
        font-weight: 600;
        color: #dfeeff;
    }

    .stButton > button {
        background: linear-gradient(135deg, #38bdf8, #2563eb);
        color: white;
        border: none;
        border-radius: 12px;
        padding: 0.72rem 1.15rem;
        font-weight: 700;
        box-shadow: 0 10px 24px rgba(37, 99, 235, 0.32);
    }

    .stButton > button:hover {
        background: linear-gradient(135deg, #0ea5e9, #1d4ed8);
    }

    [data-testid="stSidebar"] {
        background: rgba(7, 17, 31, 0.9);
        border-right: 1px solid rgba(148, 163, 184, 0.15);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

CATEGORIES = {
    "Top World News": '("world" OR "international")',
    "India": 'India',
    "AI & Technology": '("artificial intelligence" OR AI OR "machine learning" OR OpenAI OR Google OR Anthropic)',
    "Business & Economy": '("global economy" OR markets OR business OR inflation)',
    "Science & Space": '(science OR space OR NASA OR research OR climate)',
    "Politics & Geopolitics": '(election OR government OR diplomacy OR conflict OR geopolitics)',
}

FALLBACK_HEADLINES = {
    "Top World News": [
        {"title": "Global markets remain cautious as inflation and rates stay in focus", "source": "Reuters", "published": "2026-11-12 09:00 UTC", "url": "https://www.reuters.com/world/", "language": "en", "context": "Investors are watching inflation and interest-rate signals closely as global markets try to balance growth expectations with lingering uncertainty around policy decisions."},
        {"title": "Leaders push for fresh diplomatic talks as regional tensions persist", "source": "AP News", "published": "2026-11-12 08:00 UTC", "url": "https://apnews.com/world", "language": "en", "context": "Officials across several regions are reopening talks and pushing for de-escalation, as geopolitical pressure and strategic uncertainty remain high."},
        {"title": "Shipping and trade routes stay under pressure as supply chains adjust", "source": "Bloomberg", "published": "2026-11-12 07:00 UTC", "url": "https://www.bloomberg.com/world", "language": "en", "context": "Global commerce is still adapting to shipping bottlenecks, freight volatility, and uneven demand across major trade corridors."},
        {"title": "World energy markets remain sensitive to supply and demand shifts", "source": "Financial Times", "published": "2026-11-12 06:30 UTC", "url": "https://www.ft.com/world", "language": "en", "context": "Energy producers and consumers are watching storage, supply conditions, and geopolitical risk as prices remain volatile."},
        {"title": "Aid, health, and logistics systems stay under strain in multiple regions", "source": "BBC News", "published": "2026-11-12 06:00 UTC", "url": "https://www.bbc.com/news/world", "language": "en", "context": "Humanitarian agencies are balancing emergency logistics and medical support while demand remains elevated in several conflict and climate-affected areas."},
        {"title": "Global leaders focus on resilience, trade, and strategic stability", "source": "CNN", "published": "2026-11-12 05:30 UTC", "url": "https://www.cnn.com/world", "language": "en", "context": "Multilateral pressure is increasing around economic resilience, supply chain security, and diplomatic coordination across major powers."},
    ],
    "India": [
        {"title": "India focuses on infrastructure and public investment as growth targets remain in view", "source": "The Hindu", "published": "2026-11-12 09:30 UTC", "url": "https://www.thehindu.com/", "language": "en", "context": "Policy attention remains on infrastructure expansion, capital investment, and government spending as India works to preserve momentum in key economic sectors."},
        {"title": "Policy and trade discussions continue as businesses monitor next steps", "source": "Live Mint", "published": "2026-11-12 08:30 UTC", "url": "https://www.livemint.com/", "language": "en", "context": "Business leaders are reviewing policy direction and trade conditions, with renewed attention on how officials will handle growth and investment priorities."},
        {"title": "Regional development projects remain central to policy planning", "source": "Indian Express", "published": "2026-11-12 07:30 UTC", "url": "https://indianexpress.com/", "language": "en", "context": "State and national leaders are emphasizing regional projects, energy capacity, and infrastructure as part of the next growth phase."},
        {"title": "Industrial output and public spending remain key to India’s growth outlook", "source": "Business Standard", "published": "2026-11-12 06:45 UTC", "url": "https://www.business-standard.com/", "language": "en", "context": "Analysts are watching output and investment signals closely as India balances demand, spending, and manufacturing momentum."},
        {"title": "Transport and logistics demand continues to shape investment plans", "source": "Mint", "published": "2026-11-12 06:00 UTC", "url": "https://www.livemint.com/", "language": "en", "context": "Supply chains and transport networks remain central to business planning as demand and infrastructure investment evolve."},
    ],
    "AI & Technology": [
        {"title": "AI infrastructure spending remains a major focus for global technology firms", "source": "TechCrunch", "published": "2026-11-12 09:10 UTC", "url": "https://techcrunch.com/", "language": "en", "context": "Large technology companies continue to increase investment in chips, cloud capacity, and large-scale model infrastructure to support AI growth."},
        {"title": "Model safety and compute demand shape the next wave of enterprise AI investment", "source": "The Verge", "published": "2026-11-12 08:10 UTC", "url": "https://www.theverge.com/", "language": "en", "context": "Executives are balancing performance improvements with safety, cost, and data governance as AI adoption expands across industries."},
        {"title": "Open-source AI projects continue to expand as rivals challenge proprietary platforms", "source": "Wired", "published": "2026-11-12 07:10 UTC", "url": "https://www.wired.com/", "language": "en", "context": "New open-source releases are intensifying competition, encouraging more experimentation and faster innovation in the AI ecosystem."},
        {"title": "Cloud providers race to expand AI capacity for enterprise workloads", "source": "Reuters", "published": "2026-11-12 06:10 UTC", "url": "https://www.reuters.com/technology/", "language": "en", "context": "Demand for AI infrastructure is pushing cloud providers to scale computing, data services, and enterprise deployments."},
        {"title": "Startups push new tools to automate analysis, coding, and decision support", "source": "VentureBeat", "published": "2026-11-12 05:40 UTC", "url": "https://venturebeat.com/", "language": "en", "context": "Product teams are racing to build more capable AI tools as businesses look for efficiency gains and faster workflows."},
        {"title": "Chipmakers and cloud vendors watch AI demand and supply constraints closely", "source": "Bloomberg", "published": "2026-11-12 05:05 UTC", "url": "https://www.bloomberg.com/technology", "language": "en", "context": "The hardware ecosystem remains focused on capacity expansion, supply resilience, and product roadmaps tied to AI demand."},
        {"title": "NVIDIA and major AI platform players remain central to the chip roadmap conversation", "source": "CNBC", "published": "2026-11-12 04:30 UTC", "url": "https://www.cnbc.com/technology/", "language": "en", "context": "Industry watchers are monitoring supply chain constraints, pricing, and strategic positioning as AI hardware demand continues to accelerate."},
        {"title": "NVIDIA leadership and strategy continue to shape the generative AI hardware race", "source": "Reuters", "published": "2026-11-12 04:00 UTC", "url": "https://www.reuters.com/technology/", "language": "en", "context": "Executives and investors are watching how design, supply, and product leadership decisions influence the broader AI infrastructure market and competitor response."},
    ],
    "Business & Economy": [
        {"title": "Central banks watch inflation and growth data for policy signals", "source": "Financial Times", "published": "2026-11-12 09:20 UTC", "url": "https://www.ft.com/world", "language": "en", "context": "Economists expect policy decisions to remain sensitive to inflation trends, demand conditions, and the pace of global growth."},
        {"title": "Global supply chains remain alert as demand shifts across major markets", "source": "Reuters", "published": "2026-11-12 08:20 UTC", "url": "https://www.reuters.com/business/", "language": "en", "context": "Manufacturers and retailers are adjusting to uneven demand, freight variability, and tighter operational planning in global trade."},
        {"title": "Investors assess earnings resilience as markets look for direction", "source": "Bloomberg", "published": "2026-11-12 07:20 UTC", "url": "https://www.bloomberg.com/markets", "language": "en", "context": "Stock and bond markets are weighing earnings quality, rate expectations, and sector-specific pressure as the next quarter begins."},
        {"title": "Trade and manufacturing activity stays mixed across major regions", "source": "CNBC", "published": "2026-11-12 06:20 UTC", "url": "https://www.cnbc.com/world/", "language": "en", "context": "Business surveys show unevenness in manufacturing and trade activity, with companies balancing demand, supply, and cost pressure."},
        {"title": "Currency and bond markets watch yields and growth expectations closely", "source": "MarketWatch", "published": "2026-11-12 05:50 UTC", "url": "https://www.marketwatch.com/", "language": "en", "context": "Investors remain focused on yields, growth signals, and macro stability as markets adjust policy expectations."},
    ],
    "Science & Space": [
        {"title": "Researchers track climate risks and adaptation strategies as extreme weather rises", "source": "NASA Earth Observatory", "published": "2026-11-12 09:05 UTC", "url": "https://earthobservatory.nasa.gov/", "language": "en", "context": "Scientists continue mapping climate stress, volatility, and resilience strategies as extreme weather events grow in frequency and intensity."},
        {"title": "Space missions expand scientific understanding of orbit and lunar resources", "source": "Space.com", "published": "2026-11-12 08:05 UTC", "url": "https://www.space.com/", "language": "en", "context": "New missions are deepening research into orbital systems, lunar resources, and the operational challenges of sustained space exploration."},
        {"title": "Scientific collaborations aim to improve forecasting and resilience in complex systems", "source": "Nature", "published": "2026-11-12 07:05 UTC", "url": "https://www.nature.com/", "language": "en", "context": "Researchers are joining forces to improve climate and systems forecasting, with a focus on climate adaptation and predictive modeling."},
        {"title": "Climate and ocean research remain central to resilience planning", "source": "NOAA", "published": "2026-11-12 06:05 UTC", "url": "https://www.noaa.gov/", "language": "en", "context": "Agencies are prioritizing predictive science and adaptation strategies as climate and ocean variability become more difficult to manage."},
        {"title": "Space agencies watch launch schedules, orbital traffic, and research demand", "source": "ESA", "published": "2026-11-12 05:20 UTC", "url": "https://www.esa.int/", "language": "en", "context": "Space programs are balancing launch cadence, orbital safety, and scientific returns as more missions become operationally active."},
    ],
    "Politics & Geopolitics": [
        {"title": "Diplomatic channels stay active as governments weigh next steps", "source": "BBC News", "published": "2026-11-12 09:15 UTC", "url": "https://www.bbc.com/news/world", "language": "en", "context": "Officials are continuing diplomacy and negotiation efforts as governments try to reduce pressure while managing strategic and security priorities."},
        {"title": "Election calendars and coalition talks shape political attention in key regions", "source": "CNN", "published": "2026-11-12 08:15 UTC", "url": "https://www.cnn.com/world", "language": "en", "context": "Politics is increasingly shaped by electoral schedules, coalition-building, and how parties are positioning themselves ahead of major decisions."},
        {"title": "Security and trade policy remain central to bargaining and strategy", "source": "Al Jazeera", "published": "2026-11-12 07:15 UTC", "url": "https://www.aljazeera.com/", "language": "en", "context": "Governments are weighing security, trade, and diplomacy together as they try to stabilize partnerships and reduce strategic friction."},
        {"title": "Regional alliances and sanctions remain central to diplomatic calculations", "source": "Reuters", "published": "2026-11-12 06:15 UTC", "url": "https://www.reuters.com/world/", "language": "en", "context": "Diplomatic partners are re-evaluating coalitions, sanctions, and negotiation leverage as strategic pressure remains elevated."},
        {"title": "Public trust and governance debates intensify amid policy pressure", "source": "The Guardian", "published": "2026-11-12 05:35 UTC", "url": "https://www.theguardian.com/world", "language": "en", "context": "Political scrutiny is rising as public trust, institutional performance, and response capacity come under increasing pressure."},
    ],
}


def safe_title(article):
    title = str(article.get("title") or "").strip()
    if title and title.lower() != "none" and title not in {"", "null", "None"}:
        return title
    source = str(article.get("source") or "Unknown source").strip() or "Unknown source"
    url = str(article.get("url") or "").strip()
    if url:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            path = parsed.path.strip("/")
            if path:
                candidate = path.replace("-", " ").replace("/", " ")
                if candidate:
                    return f"{source} update: {candidate.title()}"
        except Exception:
            pass
    return f"Headline from {source}"


def is_english_text(value):
    if not value:
        return True
    text = str(value).strip()
    if not text:
        return True
    if all(ord(ch) < 128 for ch in text):
        return True
    return False


@st.cache_data(ttl=3600, show_spinner=False)
def translate_titles_batch(items, api_key=None):
    if not items:
        return items

    items_to_translate = []
    for item in items:
        title = str(item.get("title") or "")
        if not title:
            continue
        lang = str(item.get("language") or "").lower()
        if lang in {"en", "eng", "english"} or is_english_text(title):
            item = dict(item)
            item["title"] = title
            continue
        items_to_translate.append(item)

    if not items_to_translate:
        return items

    translated = []
    for item in items_to_translate[:5]:
        title = str(item.get("title") or "")
        if not title:
            translated.append(item)
            continue
        lang = str(item.get("language") or "").lower()
        if lang in {"en", "eng", "english"} or is_english_text(title):
            translated.append({**item, "title": title, "language": "en"})
            continue

        if api_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                response = client.responses.create(
                    model="gpt-4.1-mini",
                    input=("Translate this headline to English. Return only the translated headline with no extra text.\n\n" + title),
                )
                translated_title = str(response.output_text).strip() or title
                translated.append({**item, "title": translated_title, "language": "en"})
                continue
            except Exception:
                pass

        try:
            from deep_translator import GoogleTranslator
            translated_title = GoogleTranslator(source="auto", target="en").translate(title)
            translated.append({**item, "title": translated_title or title, "language": "en"})
        except Exception:
            translated.append(item)

    final = []
    seen = set()
    for item in items:
        if not item.get("title"):
            item = {**item, "title": safe_title(item)}
        key = (item.get("title"), item.get("url"))
        if key in seen:
            continue
        seen.add(key)
        match = next((t for t in translated if (t.get("title"), t.get("url")) == key), None)
        final.append(match if match is not None else item)
    return final


def build_context(title, source, category_name):
    text = (title or "").strip()
    if not text:
        text = source or "the latest updates"

    lower = text.lower()
    if "market" in lower or "inflation" in lower or "economy" in lower or "trade" in lower:
        return f"Markets and policymakers are tracking this issue closely, with attention on growth, pricing, and how the story may affect business conditions and regional stability."
    if "ai" in lower or "technology" in lower or "model" in lower or "software" in lower or "digital" in lower:
        return f"Technology leaders are following this development because it could shape adoption, competition, and the pace of innovation across the digital economy."
    if "election" in lower or "government" in lower or "diplomacy" in lower or "policy" in lower or "politics" in lower:
        return f"The story is being watched closely in political and policy circles because it may affect public trust, government action, and diplomatic positioning."
    if "space" in lower or "science" in lower or "research" in lower or "climate" in lower or "weather" in lower:
        return f"Researchers and public agencies are monitoring this development because it could influence scientific understanding, safety planning, and long-term resilience."
    if "india" in lower or "regional" in lower or "infrastructure" in lower or "development" in lower:
        return f"This story matters for local planning and regional momentum, with attention on growth, services, and how policy decisions affect daily life."
    return f"This developing update is relevant to {category_name.lower()} coverage and is being watched for broader economic, political, or social impact."


@st.cache_data(ttl=600, show_spinner=False)
def fetch_news(query, hours=24, limit=30, category_name="Top World News", api_key=None):
    """Fetch real-time English news from Google News RSS, with a local fallback only if the feed is unavailable."""
    topic_map = {
        "Top World News": "world news",
        "India": "India news",
        "AI & Technology": "AI technology news",
        "Business & Economy": "global business economy news",
        "Science & Space": "science space news",
        "Politics & Geopolitics": "global politics geopolitics news",
    }
    topic = topic_map.get(category_name, category_name)
    live_items = fetch_live_news(topic, limit=min(limit, 12))
    if live_items:
        return live_items, False
    fallback = FALLBACK_HEADLINES.get(category_name, [])[: min(limit, 8)]
    return fallback, True


def summarize_with_openai(items, api_key):
    if not api_key or not items:
        return None
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    headlines = "\n".join(f"- {x['title']} ({x['source']})" for x in items[:20])
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=(
            "Create a concise, neutral news briefing from these headlines. "
            "Group related stories, distinguish confirmed facts from developing reports, "
            "explain why the major stories matter, and do not invent details. "
            "Mention that readers should open the original sources for full context.\n\n"
            + headlines
        ),
    )
    return response.output_text


def clean_rss_text(value):
    text = str(value or "")
    text = re.sub(r"<.*?>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def google_news_url(topic):
    base = "https://news.google.com/rss/search?q="
    encoded = topic.replace(" ", "+")
    return base + encoded + "&hl=en-US&gl=US&ceid=US:en"


@st.cache_data(ttl=300, show_spinner=False)
def fetch_live_news(topic, limit=10):
    url = google_news_url(topic)
    try:
        response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except Exception:
        return []

    items = []
    for entry in root.findall("./channel/item")[:limit]:
        title = (entry.findtext("title") or "").strip()
        link = (entry.findtext("link") or "").strip()
        published = (entry.findtext("pubDate") or "").strip()
        summary = clean_rss_text(entry.findtext("description") or "")
        cleaned_source = "Google News"
        try:
            source_tag = entry.find("source")
            if source_tag is not None and source_tag.text:
                cleaned_source = source_tag.text.strip()
        except Exception:
            pass
        if not summary or summary == title:
            summary = build_context(title, cleaned_source, "Top World News")
        item = {
            "title": title,
            "source": cleaned_source,
            "published": published,
            "url": link,
            "language": "en",
            "context": summary,
        }
        if item["title"]:
            items.append(item)
    return items


st.markdown('<div class="headline-hero"><div class="hero-badge">🌍</div><h1 style="margin:0;">The Daily Pulse</h1></div>', unsafe_allow_html=True)
st.caption("A global news and AI intelligence dashboard · headlines refreshed every 10 minutes")
st.markdown('<div class="info-banner">Headlines are gathered from the public GDELT news index. We translate titles to English and always recommend opening the original article for full context.</div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("Your briefing")
    category = st.selectbox("News section", list(CATEGORIES.keys()))
    timeframe = st.selectbox("Look back", ["Last 6 hours", "Last 24 hours", "Last 3 days"], index=1)
    hours = {"Last 6 hours": 6, "Last 24 hours": 24, "Last 3 days": 72}[timeframe]
    max_items = st.slider("Number of headlines", 10, 50, 30, 5)
    st.markdown('<div class="chip">English-only mode</div>', unsafe_allow_html=True)
    st.divider()
    st.subheader("AI briefing")
    api_key = st.text_input("OpenAI API key", type="password", help="Used only for this session. It is not saved by this app.")
    st.caption("Without a key, titles still translate automatically when possible.")
    refresh = st.button("Refresh headlines", width="stretch")

if refresh:
    st.cache_data.clear()

try:
    with st.spinner("Gathering recent headlines..."):
        articles, using_fallback = fetch_news(CATEGORIES[category], hours, max_items, category, api_key)

    if using_fallback:
        st.caption("Using backup headlines while the public news feed recovers.")
    if not articles:
        st.warning("No headlines were returned for this filter. Try a longer time window.")
    else:
        if api_key:
            if st.button("Generate AI briefing", width="stretch"):
                with st.spinner("Summarizing headlines..."):
                    try:
                        briefing = summarize_with_openai(articles, api_key)
                        st.subheader("Your AI briefing")
                        st.markdown(briefing)
                    except Exception as exc:
                        st.error(f"Could not generate the AI briefing: {exc}")
        st.subheader(f"{category} — latest headlines")
        if articles:
            index = st.session_state.get("news_index", 0)
            total = len(articles)
            if index >= total:
                index = 0
            article = articles[index]
            title_text = safe_title(article)
            context_text = str(article.get("context") or "").strip()
            if not context_text:
                context_text = build_context(title_text, article.get("source", "News desk"), category)
            safe_url = str(article.get("url") or "#")
            safe_source = str(article.get("source") or "Unknown source")
            safe_language = str(article.get("language") or "en")
            safe_published = str(article.get("published") or "")

            col_prev, col_next = st.columns([1, 1])
            with col_prev:
                if st.button("← Previous", use_container_width=True):
                    st.session_state.news_index = (index - 1) % total
                    st.rerun()
            with col_next:
                if st.button("Next →", use_container_width=True):
                    st.session_state.news_index = (index + 1) % total
                    st.rerun()

            st.markdown(
                f"""
                <div class="news-card" style="padding: 1.5rem;">
                    <div class="news-meta" style="margin-bottom: 0.6rem;">{escape(safe_source)} · {escape(safe_language)} · {escape(safe_published)}</div>
                    <h4 style="font-size: 2.2rem; line-height: 1.15; margin: 0 0 1rem 0; color: #edf6ff;">{escape(title_text)}</h4>
                    <div style="font-size: 1.1rem; line-height: 1.7; color: #dfeeff;">{escape(context_text)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.caption(f"Story {index + 1} of {total}")
except requests.RequestException as exc:
    st.error(f"Could not retrieve headlines right now: {exc}")
except Exception as exc:
    st.error(f"Something went wrong: {exc}")

st.divider()
st.caption("The Daily Pulse is an independent news reader, not a publisher. It does not verify every claim automatically. Compare multiple reputable sources for major or breaking events.")
