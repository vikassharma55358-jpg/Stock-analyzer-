import json
import os
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
from google import genai
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st
import yfinance as yf

# Load Gemini API key from .env file
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

st.set_page_config(
    page_title="AI Stock & Fundamental Analyzer", layout="wide", page_icon="📈"
)

# ----------------- CUSTOM THEME: DARK TRADING-DESK LOOK -----------------
st.markdown(
    """
    <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=IBM+Plex+Mono:wght@400;600&display=swap" rel="stylesheet">
    <style>
    :root {
        --td-bg: #0B1220;
        --td-card: #141B2E;
        --td-border: #232C42;
        --td-text: #F4F1EA;
        --td-muted: #8A93A6;
        --td-amber: #EF9F27;
        --td-teal: #5DCAA5;
        --td-coral: #F0997B;
    }
    .stApp { background-color: var(--td-bg); color: var(--td-text); }
    h1, h2, h3 { font-family: 'Space Grotesk', sans-serif !important; color: var(--td-text) !important; }
    [data-testid="stMetricValue"], [data-testid="stMetricDelta"] {
        font-family: 'IBM Plex Mono', monospace !important;
        color: var(--td-text) !important;
    }
    [data-testid="stMetricLabel"] { color: var(--td-muted) !important; }
    [data-testid="stMetric"] {
        background: var(--td-card);
        border-left: 3px solid var(--td-amber);
        border-radius: 0 8px 8px 0;
        padding: 12px 14px;
    }
    [data-testid="stSidebar"] { background-color: var(--td-card); }
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: var(--td-text) !important;
    }
    [data-testid="stCaptionContainer"], .stCaption, small {
        color: var(--td-muted) !important;
    }
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] span,
    [data-testid="stMarkdownContainer"] li {
        color: var(--td-text);
    }
    [data-testid="stTabs"] button p { color: var(--td-muted) !important; }
    [data-testid="stTabs"] button[aria-selected="true"] p {
        color: var(--td-amber) !important;
    }
    [data-testid="stTabs"] button[aria-selected="true"] {
        border-bottom-color: var(--td-amber) !important;
    }
    div[data-baseweb="tab-list"] { border-bottom: 1px solid var(--td-border); }
    .stButton button {
        font-family: 'Space Grotesk', sans-serif;
        border-radius: 6px;
    }
    /* Scrolling ticker tape */
    .ticker-wrap {
        overflow: hidden;
        white-space: nowrap;
        background: var(--td-card);
        border-left: 3px solid var(--td-amber);
        border-radius: 6px;
        padding: 8px 0;
        margin-bottom: 18px;
    }
    .ticker-move {
        display: inline-block;
        padding-left: 100%;
        animation: ticker-scroll 25s linear infinite;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 13px;
    }
    .ticker-move span { padding: 0 22px; }
    .tick-up { color: var(--td-teal); }
    .tick-down { color: var(--td-coral); }
    @keyframes ticker-scroll {
        0% { transform: translateX(0); }
        100% { transform: translateX(-100%); }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------- PORTFOLIO PERSISTENCE (saved to a JSON file on disk) -----------------
PORTFOLIO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio_data.json")


def load_portfolio():
    """Load saved portfolio (ticker -> {quantity, buy_price}) from disk, or return defaults."""
    try:
        if os.path.exists(PORTFOLIO_FILE):
            with open(PORTFOLIO_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    # Default starter list — quantity/buy_price are 0 until user fills them in
    return {
        "RELIANCE.NS": {"quantity": 0.0, "buy_price": 0.0},
        "TATAMOTORS.NS": {"quantity": 0.0, "buy_price": 0.0},
        "SJVN.NS": {"quantity": 0.0, "buy_price": 0.0},
        "AAPL": {"quantity": 0.0, "buy_price": 0.0},
    }


def save_portfolio(data):
    """Persist the portfolio dict to disk so it survives app restarts."""
    try:
        with open(PORTFOLIO_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


# Initialize Portfolio/Watchlist in Session State
# Structure: { "TICKER": {"quantity": float, "buy_price": float}, ... }
if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_portfolio()

st.title("📈 AI Stock, News & Smart Entry Evaluator")


# ----------------- LIVE SCROLLING TICKER TAPE -----------------
@st.cache_data(ttl=120)
def get_ticker_tape_data(symbols):
    rows = []
    for sym in symbols:
        try:
            t_info = yf.Ticker(sym).info or {}
            price = t_info.get("currentPrice", t_info.get("regularMarketPrice"))
            prev = t_info.get("previousClose", price)
            if isinstance(price, (int, float)) and isinstance(prev, (int, float)) and prev != 0:
                pct = (price - prev) / prev * 100
            else:
                pct = 0.0
            rows.append((sym, price, pct))
        except Exception:
            continue
    return rows


def render_ticker_tape():
    symbols = list(st.session_state.watchlist.keys()) or ["RELIANCE.NS", "AAPL"]
    data = get_ticker_tape_data(tuple(symbols))
    if not data:
        return
    spans = ""
    for sym, price, pct in data:
        css_class = "tick-up" if pct >= 0 else "tick-down"
        arrow = "▲" if pct >= 0 else "▼"
        price_str = f"{price:,.2f}" if isinstance(price, (int, float)) else "N/A"
        spans += f'<span class="{css_class}">{sym} {price_str} {arrow}{abs(pct):.2f}%</span>'
    html = f'<div class="ticker-wrap"><div class="ticker-move">{spans}{spans}</div></div>'
    st.markdown(html, unsafe_allow_html=True)


render_ticker_tape()

POPULAR_STOCKS = {
    "Reliance Industries": "RELIANCE.NS",
    "Tata Steel": "TATASTEEL.NS",
    "Hero MotoCorp": "HEROMOTOCO.NS",
    "SJVN Ltd": "SJVN.NS",
    "Hindustan Copper": "HINDCOPPER.NS",
    "HDFC Bank": "HDFCBANK.NS",
    "ICICI Bank": "ICICIBANK.NS",
    "Tata Motors": "TATAMOTORS.NS",
    "Infosys": "INFY.NS",
    "State Bank of India (SBI)": "SBIN.NS",
    "Bajaj Finance": "BAJFINANCE.NS",
    "Jio Financial Services": "JIOFIN.NS",
    "Apple Inc. (US)": "AAPL",
    "Nvidia Corporation (US)": "NVDA",
    "Tesla (US)": "TSLA",
    "Microsoft (US)": "MSFT",
}


# ----------------- SECTOR-WISE PEER MAPPING (for auto stock comparison) -----------------
SECTOR_PEERS = {
    "technology": ["TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS", "TECHM.NS"],
    "software": ["TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS"],
    "banking": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS"],
    "financial services": ["HDFCBANK.NS", "ICICIBANK.NS", "BAJFINANCE.NS", "SBIN.NS"],
    "automobile": ["TATAMOTORS.NS", "MARUTI.NS", "M&M.NS", "BAJAJ-AUTO.NS", "HEROMOTOCO.NS"],
    "auto": ["TATAMOTORS.NS", "MARUTI.NS", "M&M.NS", "HEROMOTOCO.NS"],
    "energy": ["RELIANCE.NS", "ONGC.NS", "IOC.NS", "BPCL.NS"],
    "oil & gas": ["RELIANCE.NS", "ONGC.NS", "IOC.NS", "BPCL.NS"],
    "basic materials": ["TATASTEEL.NS", "HINDALCO.NS", "JSWSTEEL.NS", "HINDCOPPER.NS"],
    "metal": ["TATASTEEL.NS", "HINDALCO.NS", "JSWSTEEL.NS", "HINDCOPPER.NS"],
    "healthcare": ["SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS"],
    "pharma": ["SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS"],
    "consumer cyclical": ["TITAN.NS", "TRENT.NS", "DMART.NS"],
    "consumer defensive": ["HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS"],
    "communication services": ["BHARTIARTL.NS", "IDEA.NS"],
    "utilities": ["NTPC.NS", "SJVN.NS", "POWERGRID.NS"],
    "consumer electronics": ["AAPL", "MSFT", "NVDA"],
}

DEFAULT_PEERS = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS"]


def get_auto_peers(symbol, sector, industry):
    """Suggest 3-4 peer tickers based on the stock's sector/industry, excluding itself."""
    key_source = f"{sector or ''} {industry or ''}".lower()
    for key, peers in SECTOR_PEERS.items():
        if key in key_source:
            filtered = [p for p in peers if p != symbol]
            if filtered:
                return filtered[:4]
    # Fallback: a few generic large-caps, excluding the stock itself
    return [p for p in DEFAULT_PEERS if p != symbol][:3]


def get_price_range_peers(symbol, current_price, currency, max_results=4, tolerance=0.25):
    """Find peer stocks whose CURRENT PRICE is close to this stock's price
    (same currency market only, so INR stocks compare with INR and USD with USD)."""
    if not isinstance(current_price, (int, float)) or current_price <= 0:
        return [p for p in DEFAULT_PEERS if p != symbol][:max_results]

    # Build a candidate pool from everything we already know about
    candidate_pool = set()
    for peers in SECTOR_PEERS.values():
        candidate_pool.update(peers)
    candidate_pool.update(POPULAR_STOCKS.values())
    candidate_pool.discard(symbol)

    scored = []
    for cand in candidate_pool:
        data = fetch_comparison_data(cand)
        price = data.get("Price")
        cand_currency = data.get(
            "Currency", "INR" if cand.endswith(".NS") else "USD"
        )
        if cand_currency != currency:
            continue
        if isinstance(price, (int, float)) and price > 0:
            diff_pct = abs(price - current_price) / current_price
            scored.append((diff_pct, cand))

    scored.sort(key=lambda x: x[0])

    # Prefer close matches within the tolerance band; if not enough, take closest anyway
    close_matches = [c for d, c in scored if d <= tolerance][:max_results]
    if len(close_matches) < 2:
        close_matches = [c for _, c in scored[:max_results]]

    return close_matches if close_matches else [p for p in DEFAULT_PEERS if p != symbol][:max_results]


# ----------------- NAME -> TICKER SEARCH -----------------
@st.cache_data(ttl=3600)
def search_stock_by_name(query):
    """Search Yahoo Finance for a ticker matching a general company name.
    Returns a list of dicts: [{"symbol": "TSLA", "name": "Tesla, Inc."}, ...]
    """
    if not query or len(query.strip()) < 2:
        return []

    results = []

    # 1. Try yfinance's built-in search (covers global stocks, not just our list)
    try:
        search_result = yf.Search(query, max_results=8)
        for quote in search_result.quotes:
            symbol = quote.get("symbol")
            name = quote.get("shortname") or quote.get("longname") or symbol
            if symbol:
                results.append({"symbol": symbol, "name": name})
    except Exception:
        pass

    # 2. Fallback / supplement: substring match against our curated list
    if not results:
        q = query.strip().lower()
        for name, symbol in POPULAR_STOCKS.items():
            if q in name.lower():
                results.append({"symbol": symbol, "name": name})

    return results


# ----------------- SIDEBAR -----------------
st.sidebar.header("🔍 Stock Finder")

st.sidebar.markdown("**Search by Company Name:**")
name_query = st.sidebar.text_input(
    "e.g. Tesla, Reliance, Apple",
    value="",
    key="name_search_box",
    placeholder="Type a company name...",
)

selected_from_search = None
if name_query.strip():
    matches = search_stock_by_name(name_query)
    if matches:
        options = [f"{m['name']} ({m['symbol']})" for m in matches]
        picked = st.sidebar.selectbox(
            "Matching stocks — pick one:",
            options=["-- Select --"] + options,
            key="search_match_select",
        )
        if picked != "-- Select --":
            idx = options.index(picked)
            selected_from_search = matches[idx]["symbol"]
    else:
        st.sidebar.caption("No matches found. Try a different name or use the ticker box below.")

st.sidebar.markdown("---")

# Popular stocks dropdown
selected_company = st.sidebar.selectbox(
    "Or select from Popular Stocks:",
    options=["-- Select Stock --"] + list(POPULAR_STOCKS.keys()),
)

# Text Input for ANY stock symbol
st.sidebar.markdown("**OR Enter Any Ticker Symbol:**")
manual_ticker = st.sidebar.text_input(
    "Symbol (e.g., NHPC.NS, SBIN.NS, TSLA):",
    value="",
    placeholder="e.g. NHPC.NS",
).strip().upper()

# Logic: Manual ticker > Name search result > Popular dropdown > default
if manual_ticker:
    ticker = manual_ticker
elif selected_from_search:
    ticker = selected_from_search
elif selected_company != "-- Select Stock --":
    ticker = POPULAR_STOCKS[selected_company]
else:
    ticker = "RELIANCE.NS"  # Default fallback

st.sidebar.caption("💡 **Tip:** Indian stocks ke aage `.NS` zaroor lagayein (e.g., `NHPC.NS`).")

st.sidebar.markdown("---")
st.sidebar.subheader("📌 Common Stock Symbols")
ref_df = pd.DataFrame(
    list(POPULAR_STOCKS.items()), columns=["Company Name", "Symbol"]
)
st.sidebar.dataframe(ref_df, hide_index=True, use_container_width=True)

# --- PORTFOLIO / WATCHLIST MANAGER ---
st.sidebar.markdown("---")
st.sidebar.subheader("⭐ Portfolio Manager")
st.sidebar.caption("Quantity & buy price daalo taaki P&L track ho sake (0 chhod sakte ho sirf watch karne ke liye).")

add_qty = st.sidebar.number_input(
    "Quantity", min_value=0.0, value=1.0, step=1.0, key="add_qty_input"
)
add_buy_price = st.sidebar.number_input(
    f"Your Buy Price ({ticker}):", min_value=0.0, value=0.0, step=1.0, key="add_buy_price_input"
)

if st.sidebar.button(f"➕ Add '{ticker}' to Portfolio"):
    st.session_state.watchlist[ticker] = {
        "quantity": add_qty,
        "buy_price": add_buy_price,
    }
    save_portfolio(st.session_state.watchlist)
    st.sidebar.success(f"Added {ticker} ({add_qty} qty @ {add_buy_price})!")
    st.rerun()

if st.session_state.watchlist:
    selected_to_remove = st.sidebar.selectbox(
        "Remove Stock:",
        options=["Select Stock"] + list(st.session_state.watchlist.keys()),
        key="remove_stock_select",
    )
    if selected_to_remove != "Select Stock":
        if st.sidebar.button(f"❌ Remove {selected_to_remove}"):
            del st.session_state.watchlist[selected_to_remove]
            save_portfolio(st.session_state.watchlist)
            st.sidebar.success(f"Removed {selected_to_remove}")
            st.rerun()


# ----------------- CACHED DATA FETCHERS (YFINANCE) -----------------
@st.cache_data(ttl=300)
def fetch_stock_data(symbol):
    try:
        stock = yf.Ticker(symbol)

        # 1. Historical Chart Data
        df = stock.history(period="1y")
        if df.empty:
            return None, {}, {}

        df = df.reset_index()

        # SMA
        df["SMA_50"] = df["Close"].rolling(window=50).mean()
        df["SMA_200"] = df["Close"].rolling(window=200).mean()

        # Safe RSI (14 Days)
        delta = df["Close"].diff()
        gain = delta.clip(lower=0).rolling(window=14).mean()
        loss = (-delta.clip(upper=0)).rolling(window=14).mean()

        # Prevent division by zero
        rs = gain / loss.replace(0, 1e-10)
        df["RSI_14"] = 100 - (100 / (1 + rs))

        # Bollinger Bands
        df["BB_Middle"] = df["Close"].rolling(window=20).mean()
        df["BB_Std"] = df["Close"].rolling(window=20).std()
        df["BB_Upper"] = df["BB_Middle"] + (df["BB_Std"] * 2)
        df["BB_Lower"] = df["BB_Middle"] - (df["BB_Std"] * 2)

        # MACD
        exp1 = df["Close"].ewm(span=12, adjust=False).mean()
        exp2 = df["Close"].ewm(span=26, adjust=False).mean()
        df["MACD"] = exp1 - exp2
        df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
        df["MACD_Hist"] = df["MACD"] - df["MACD_Signal"]

        # 2. Key Metadata & Fundamentals
        info = stock.info or {}

        meta = {
            "regularMarketPrice": info.get(
                "currentPrice",
                info.get("regularMarketPrice", float(df["Close"].iloc[-1])),
            ),
            "chartPreviousClose": info.get(
                "previousClose",
                (
                    float(df["Close"].iloc[-2])
                    if len(df) > 1
                    else float(df["Close"].iloc[-1])
                ),
            ),
            "currency": info.get("currency", "INR" if symbol.endswith(".NS") else "USD"),
        }

        return df, meta, info
    except Exception as e:
        st.error(f"Error loading stock data: {e}")
        return None, {}, {}


@st.cache_data(ttl=600)
def fetch_stock_news(search_term):
    url = f"https://news.google.com/rss/search?q={search_term}+stock+news&hl=en-IN&gl=IN&ceid=IN:en"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
    }
    news_items = []

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item")[:7]:
                title = (
                    item.find("title").text
                    if item.find("title") is not None
                    else ""
                )
                link = (
                    item.find("link").text
                    if item.find("link") is not None
                    else ""
                )
                pub_date = (
                    item.find("pubDate").text
                    if item.find("pubDate") is not None
                    else ""
                )
                news_items.append(
                    {"title": title, "link": link, "date": pub_date}
                )
    except Exception:
        pass

    return news_items


@st.cache_data(ttl=900)
def fetch_ipo_news():
    """Fetch recent IPO-related news headlines (mainboard + SME, India-focused)."""
    url = "https://news.google.com/rss/search?q=upcoming+IPO+stock+market+india&hl=en-IN&gl=IN&ceid=IN:en"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
    }
    news_items = []

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item")[:10]:
                title = (
                    item.find("title").text
                    if item.find("title") is not None
                    else ""
                )
                link = (
                    item.find("link").text
                    if item.find("link") is not None
                    else ""
                )
                pub_date = (
                    item.find("pubDate").text
                    if item.find("pubDate") is not None
                    else ""
                )
                news_items.append(
                    {"title": title, "link": link, "date": pub_date}
                )
    except Exception:
        pass

    return news_items


# ----------------- AI GENERATORS WITH GOOGLE SEARCH GROUNDING -----------------
def evaluate_custom_buy_price(
    ticker_sym, user_price, curr_price, target_mean, rsi, pe, key
):
    try:
        client = genai.Client(api_key=key)
        prompt = f"""
        Act as a professional Stock Trader & Risk Manager.
        User wants to buy the stock '{ticker_sym}' at price: {user_price}
        
        Stock Current Market Data:
        - Live Market Price: {curr_price}
        - Analyst Target Price: {target_mean}
        - RSI (14 Days): {rsi}
        - P/E Ratio: {pe}
        
        Use live search to see any latest breaking news or structural triggers for {ticker_sym}.
        Answer clearly in simple Hinglish (mix of Hindi + English):
        1. **Verdict**: Should the user buy at {user_price}? (GOOD ENTRY / RISKY / WAIT FOR DIP)
        2. **Risk to Reward Ratio**: Evaluate if buying at {user_price} leaves enough profit upside compared to the Target ({target_mean}).
        3. **Suggested Entry Zone & Stop Loss**: Give a clear suggested buying range and strict stop-loss price.
        Keep it direct and actionable with bullet points.
        """
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={"tools": [{"google_search": {}}]}
        )
        return response.text
    except Exception as e:
        return f"AI Evaluation Error: {e}"


def analyze_news_sentiment(news_list, ticker_sym, key):
    try:
        client = genai.Client(api_key=key)
        headlines = "\n".join([f"- {n['title']}" for n in news_list])
        prompt = f"""
        Analyze these recent news headlines for {ticker_sym}:
        {headlines}
        
        Search for any additional real-time updates/breaking news about {ticker_sym} online.
        Provide a response in simple Hinglish:
        1. Overall News Sentiment: (BULLISH 🟢 / BEARISH 🔴 / NEUTRAL 🟡)
        2. Key Market Catalysts or Deals mentioned.
        3. Short-term price impact.
        """
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={"tools": [{"google_search": {}}]}
        )
        return response.text
    except Exception as e:
        return f"AI Sentiment Error: {e}"


def get_ai_analysis(
    ticker_sym, curr_price, target_mean, rec_key, rsi, pe, key
):
    try:
        client = genai.Client(api_key=key)
        prompt = f"""
        Act as a top stock analyst. Analyze '{ticker_sym}'.
        - Current Price: {curr_price}
        - Target Price: {target_mean}
        - Consensus Rating: {rec_key}
        - RSI: {rsi}
        - P/E: {pe}
        
        Perform a live Google Search to fetch recent quarterly results, corporate actions, or major market developments for '{ticker_sym}'.
        
        Provide a research report in Hinglish:
        1. Verdict (BUY / HOLD / SELL)
        2. Valuation check (P/E & RSI)
        3. Live Catalysts / Market Factors (from real-time web search)
        4. Target & Key Risks.
        """
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={"tools": [{"google_search": {}}]}
        )
        return response.text
    except Exception as e:
        return f"AI Generation Error: {e}"


def get_ipo_suggestions(key, risk_profile="Moderate"):
    try:
        client = genai.Client(api_key=key)
        prompt = f"""
        Act as an IPO Research Analyst covering the Indian stock market (NSE/BSE mainboard
        and SME IPOs), and also major global IPOs if relevant.

        Use live Google Search to find:
        1. IPOs that are CURRENTLY OPEN for subscription today.
        2. IPOs opening in the next 1-2 weeks (upcoming).
        3. Their price band, lot size, subscription status (if open), and Grey Market
           Premium (GMP) if available.

        User's risk profile: {risk_profile}

        Respond in simple Hinglish (Hindi + English mix), structured like this:
        1. **Currently Open IPOs**: list each with price band, subscription status, GMP, and
           a short verdict (SUBSCRIBE / AVOID / RISKY) based on fundamentals and market buzz.
        2. **Upcoming IPOs (next 1-2 weeks)**: list each with expected price band and what
           the company does.
        3. **Top Pick(s)**: based on the user's risk profile, highlight 1-2 IPOs that look
           most promising and briefly explain why.
        4. Add a short disclaimer that this is AI-generated research, not financial advice,
           and IPO investing carries risk including listing losses.

        Keep it concise and use bullet points.
        """
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={"tools": [{"google_search": {}}]}
        )
        return response.text
    except Exception as e:
        return f"AI IPO Suggestion Error: {e}"


@st.cache_data(ttl=300)
def fetch_comparison_data(symbol):
    """Fetch a compact set of metrics for the stock comparison table."""
    try:
        stock = yf.Ticker(symbol)
        info = stock.info or {}
        price = info.get("currentPrice", info.get("regularMarketPrice", "N/A"))
        pe = info.get("trailingPE", info.get("forwardPE", "N/A"))
        pb = info.get("priceToBook", "N/A")
        target = info.get("targetMeanPrice", "N/A")
        rec = str(info.get("recommendationKey", "N/A")).upper()
        mcap = info.get("marketCap", "N/A")
        currency = info.get("currency", "INR" if symbol.endswith(".NS") else "USD")

        return {
            "Ticker": symbol,
            "Price": round(price, 2) if isinstance(price, (int, float)) else "N/A",
            "P/E": round(pe, 2) if isinstance(pe, (int, float)) else "N/A",
            "P/B": round(pb, 2) if isinstance(pb, (int, float)) else "N/A",
            "Target Price": round(target, 2) if isinstance(target, (int, float)) else "N/A",
            "Recommendation": rec,
            "Market Cap": format_market_cap(mcap, symbol),
            "Currency": currency,
        }
    except Exception:
        return {
            "Ticker": symbol,
            "Price": "N/A",
            "P/E": "N/A",
            "P/B": "N/A",
            "Target Price": "N/A",
            "Recommendation": "N/A",
            "Market Cap": "N/A",
            "Currency": "N/A",
        }


def get_comparison_suggestion(primary_ticker, comparison_rows, key):
    try:
        client = genai.Client(api_key=key)
        rows_text = "\n".join(
            f"- {r['Ticker']}: Price={r['Price']}, P/E={r['P/E']}, P/B={r['P/B']}, "
            f"Target Price={r['Target Price']}, Recommendation={r['Recommendation']}, "
            f"Market Cap={r['Market Cap']}"
            for r in comparison_rows
        )
        prompt = f"""
        The user is planning to buy the stock '{primary_ticker}' and wants to compare it
        against a few alternative stocks before deciding where to put their money.

        Comparison data:
        {rows_text}

        Use live Google Search to check recent news, results, or developments for these
        stocks that could affect the decision.

        Answer in simple Hinglish (Hindi + English mix):
        1. **Best Pick**: Among all the stocks listed (including '{primary_ticker}'), which
           one looks like the best buy right now, and why.
        2. **Why not the others**: One short line each on why the other stocks are
           relatively weaker choices right now.
        3. **Final Verdict on '{primary_ticker}'**: Should the user go ahead and buy
           '{primary_ticker}' specifically, or is there a clearly better alternative here?
        Keep it concise, use bullet points, be direct.
        """
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={"tools": [{"google_search": {}}]}
        )
        return response.text
    except Exception as e:
        return f"AI Comparison Error: {e}"


def format_market_cap(val, symbol):
    if val == "N/A" or not isinstance(val, (int, float)):
        return "N/A"
    if val >= 1e12:
        return (
            f"₹{val / 1e12:.2f} Lakh Cr"
            if "NS" in symbol
            else f"${val / 1e12:.2f}T"
        )
    elif val >= 1e7 and "NS" in symbol:
        return f"₹{val / 1e7:.2f} Cr"
    elif val >= 1e9:
        return f"${val / 1e9:.2f}B"
    return f"{val}"


# ----------------- MAIN UI -----------------
analyze_btn = st.sidebar.button("Analyze Stock 🚀")

if analyze_btn or ticker:
    with st.spinner(f"Fetching Data, Fundamentals & News for {ticker}..."):
        df, meta, info = fetch_stock_data(ticker)
        clean_symbol = ticker.replace(".NS", "")
        news_data = fetch_stock_news(clean_symbol)

        if df is None or df.empty:
            st.error(f"'{ticker}' ka Data nahi mila! Please check symbol.")
        else:
            curr_price = float(
                meta.get("regularMarketPrice", df["Close"].iloc[-1])
            )
            prev_close = float(meta.get("chartPreviousClose", curr_price))

            change = curr_price - prev_close
            pct_change = (change / prev_close * 100) if prev_close != 0 else 0
            currency = meta.get("currency", "INR")

            # Fundamental Data Extracts
            mcap_raw = info.get("marketCap", "N/A")
            mcap_str = format_market_cap(mcap_raw, ticker)

            pe_ratio = info.get("trailingPE", info.get("forwardPE", "N/A"))
            pe_str = (
                f"{pe_ratio:.2f}"
                if isinstance(pe_ratio, (int, float))
                else "N/A"
            )

            raw_target = info.get("targetMeanPrice", "N/A")
            target_mean = (
                float(raw_target)
                if isinstance(raw_target, (int, float))
                else "N/A"
            )
            rec_key = str(info.get("recommendationKey", "N/A")).upper()

            latest_rsi = (
                f"{df['RSI_14'].iloc[-1]:.1f}"
                if not pd.isna(df["RSI_14"].iloc[-1])
                else "N/A"
            )

            # Top Metrics Dashboard
            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("Current Price", f"{currency} {curr_price:.2f}")
            c2.metric("1-Day Change", f"{change:+.2f} ({pct_change:+.2f}%)")
            c3.metric("Market Cap", mcap_str)
            c4.metric("P/E Ratio", pe_str)
            c5.metric("RSI (14)", latest_rsi)
            c6.metric(
                "Brokerage Target",
                f"{currency} {target_mean}"
                if isinstance(target_mean, (int, float))
                else "N/A",
            )

            st.markdown("---")

            tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
                "💡 Buy/Sell Evaluator",
                "📊 Price & Technicals",
                "🏛️ Company Fundamentals",
                "🎯 Brokerage Targets",
                "📰 News & Sentiment",
                "🤖 AI Financial Verdict",
                "⭐ My Watchlist",
                "🆕 IPO Suggestions",
                "🆚 Compare & Suggest",
            ])

            # TAB 1: BUY/SELL EVALUATOR
            with tab1:
                st.subheader("🎯 Custom Entry Price & Buy/Sell Evaluator")
                st.caption(
                    "Yahan aap jis price par stock buy karna chahte ho woh daal"
                    " kar AI se entry signal check kar sakte ho."
                )

                col_input, col_eval = st.columns([0.4, 0.6])

                with col_input:
                    user_buy_price = st.number_input(
                        f"Enter your Buying Target Price ({currency}):",
                        min_value=0.0,
                        value=float(curr_price),
                        step=1.0,
                    )

                    diff_from_current = (
                        (user_buy_price - curr_price) / curr_price
                    ) * 100

                    st.write(
                        f"**Live Market Price:** {currency} {curr_price:.2f}"
                    )
                    if diff_from_current < 0:
                        st.info(
                            f"📉 Your target is **{abs(diff_from_current):.2f}%"
                            " LOWER** than current price (Buying at a Dip)."
                        )
                    elif diff_from_current > 0:
                        st.warning(
                            f"📈 Your target is **{diff_from_current:.2f}%"
                            " HIGHER** than current price (Buying at a"
                            " Premium)."
                        )
                    else:
                        st.write(
                            "ℹ️ Target is equal to Current Price (Immediate"
                            " Entry)."
                        )

                    if isinstance(target_mean, (int, float)) and user_buy_price > 0:
                        potential_gain = (
                            (target_mean - user_buy_price) / user_buy_price
                        ) * 100
                        st.metric(
                            "Potential Gain (Till Analyst Target)",
                            f"{potential_gain:+.2f}%",
                        )

                    eval_btn = st.button("Evaluate Entry Signal 🚀")

                with col_eval:
                    if eval_btn:
                        if GEMINI_API_KEY:
                            with st.spinner(
                                "Analyzing risk/reward ratio with live web search..."
                            ):
                                eval_report = evaluate_custom_buy_price(
                                    ticker,
                                    user_buy_price,
                                    curr_price,
                                    target_mean,
                                    latest_rsi,
                                    pe_str,
                                    GEMINI_API_KEY,
                                )
                                st.markdown("### 🤖 Entry Signal Report")
                                st.markdown(eval_report)
                        else:
                            st.error(
                                "`.env` file me GEMINI_API_KEY set nahi hai."
                            )
                    else:
                        st.info(
                            "👈 Left side par price enter karke **'Evaluate"
                            " Entry Signal'** button par click karein."
                        )

            # TAB 2: TECHNICAL CHARTS
            with tab2:
                st.subheader(
                    "📊 Advanced Technical Chart (Bollinger Bands, RSI & MACD)"
                )

                fig = make_subplots(
                    rows=3,
                    cols=1,
                    shared_xaxes=True,
                    vertical_spacing=0.05,
                    row_heights=[0.5, 0.25, 0.25],
                    subplot_titles=(
                        "Price, SMA & Bollinger Bands",
                        "RSI (14)",
                        "MACD (12, 26, 9)",
                    ),
                )

                fig.add_trace(
                    go.Candlestick(
                        x=df["Date"],
                        open=df["Open"],
                        high=df["High"],
                        low=df["Low"],
                        close=df["Close"],
                        name="Price",
                    ),
                    row=1,
                    col=1,
                )
                fig.add_trace(
                    go.Scatter(
                        x=df["Date"],
                        y=df["BB_Upper"],
                        line=dict(color="rgba(173, 216, 230, 0.5)", width=1),
                        name="BB Upper",
                    ),
                    row=1,
                    col=1,
                )
                fig.add_trace(
                    go.Scatter(
                        x=df["Date"],
                        y=df["BB_Lower"],
                        line=dict(color="rgba(173, 216, 230, 0.5)", width=1),
                        fill="tonexty",
                        fillcolor="rgba(173, 216, 230, 0.1)",
                        name="BB Lower",
                    ),
                    row=1,
                    col=1,
                )
                fig.add_trace(
                    go.Scatter(
                        x=df["Date"],
                        y=df["SMA_50"],
                        line=dict(color="orange", width=1.2),
                        name="50 SMA",
                    ),
                    row=1,
                    col=1,
                )
                fig.add_trace(
                    go.Scatter(
                        x=df["Date"],
                        y=df["SMA_200"],
                        line=dict(color="cyan", width=1.2),
                        name="200 SMA",
                    ),
                    row=1,
                    col=1,
                )

                # RSI
                fig.add_trace(
                    go.Scatter(
                        x=df["Date"],
                        y=df["RSI_14"],
                        line=dict(color="purple", width=1.5),
                        name="RSI",
                    ),
                    row=2,
                    col=1,
                )
                fig.add_hline(
                    y=70, line_dash="dash", line_color="red", row=2, col=1
                )
                fig.add_hline(
                    y=30, line_dash="dash", line_color="green", row=2, col=1
                )

                # MACD
                fig.add_trace(
                    go.Scatter(
                        x=df["Date"],
                        y=df["MACD"],
                        line=dict(color="blue", width=1.5),
                        name="MACD",
                    ),
                    row=3,
                    col=1,
                )
                fig.add_trace(
                    go.Scatter(
                        x=df["Date"],
                        y=df["MACD_Signal"],
                        line=dict(color="orange", width=1.5, dash="dot"),
                        name="Signal",
                    ),
                    row=3,
                    col=1,
                )

                colors = [
                    "green" if val >= 0 else "red" for val in df["MACD_Hist"]
                ]
                fig.add_trace(
                    go.Bar(
                        x=df["Date"],
                        y=df["MACD_Hist"],
                        marker_color=colors,
                        name="Histogram",
                    ),
                    row=3,
                    col=1,
                )

                fig.update_layout(
                    xaxis_rangeslider_visible=False,
                    template="plotly_dark",
                    height=750,
                )
                st.plotly_chart(fig, use_container_width=True)

            # TAB 3: FUNDAMENTALS
            with tab3:
                st.subheader("🏛️ Key Fundamental Metrics")
                f1, f2, f3 = st.columns(3)
                with f1:
                    st.markdown(f"**Market Capitalization:** `{mcap_str}`")
                    st.markdown(f"**P/E Ratio:** `{pe_str}`")
                    pb_ratio = info.get("priceToBook", "N/A")
                    st.markdown(
                        f"**P/B Ratio:**"
                        f" `{pb_ratio:.2f}`"
                        if isinstance(pb_ratio, (int, float))
                        else f"**P/B Ratio:** `{pb_ratio}`"
                    )

                with f2:
                    high_52 = info.get("fiftyTwoWeekHigh", "N/A")
                    low_52 = info.get("fiftyTwoWeekLow", "N/A")
                    st.markdown(f"**52-Week High:** {currency} {high_52}")
                    st.markdown(f"**52-Week Low:** {currency} {low_52}")
                    div_yield = info.get("dividendYield", "N/A")
                    st.markdown(
                        f"**Dividend Yield:**"
                        f" `{div_yield * 100:.2f}%`"
                        if isinstance(div_yield, (int, float))
                        else f"**Dividend Yield:** `{div_yield}`"
                    )

                with f3:
                    roe = info.get("returnOnEquity", "N/A")
                    st.markdown(
                        f"**ROE:**"
                        f" `{roe * 100:.2f}%`"
                        if isinstance(roe, (int, float))
                        else f"**ROE:** `{roe}`"
                    )
                    profit_margins = info.get("profitMargins", "N/A")
                    st.markdown(
                        f"**Profit Margin:**"
                        f" `{profit_margins * 100:.2f}%`"
                        if isinstance(profit_margins, (int, float))
                        else f"**Profit Margin:** `{profit_margins}`"
                    )

            # TAB 4: BROKERAGE TARGETS & NEWS REPORTS
            with tab4:
                st.subheader("🎯 Brokerage Firm Targets & Recommendations")

                target_high = info.get("targetHighPrice", "N/A")
                target_low = info.get("targetLowPrice", "N/A")
                num_analysts = info.get("numberOfAnalystOpinions", "N/A")

                st.write(
                    f"**Mean Target:** {currency} {target_mean} | **High"
                    f" Target:** {currency} {target_high} | **Low Target:**"
                    f" {currency} {target_low}"
                )
                st.write(
                    f"**Consensus Recommendation:** `{rec_key}` (Total Analysts:"
                    f" **{num_analysts}**)"
                )

                st.markdown("---")
                st.markdown("### 🏢 Recent Brokerage Firm Reports & News")

                has_yahoo_data = False
                try:
                    stock_obj = yf.Ticker(ticker)
                    upgrades = stock_obj.upgrades_downgrades
                    if upgrades is not None and not upgrades.empty:
                        df_upgrades = upgrades.reset_index().head(10)
                        cols_available = [
                            col
                            for col in [
                                "GradeDate",
                                "Firm",
                                "ToGrade",
                                "FromGrade",
                                "Action",
                            ]
                            if col in df_upgrades.columns
                        ]
                        df_display = df_upgrades[cols_available].copy()
                        if "GradeDate" in df_display.columns:
                            df_display["GradeDate"] = pd.to_datetime(
                                df_display["GradeDate"]
                            ).dt.strftime("%Y-%m-%d")
                        df_display.rename(
                            columns={
                                "GradeDate": "Date",
                                "Firm": "Brokerage Firm Name",
                                "ToGrade": "New Rating",
                                "FromGrade": "Old Rating",
                                "Action": "Action Taken",
                            },
                            inplace=True,
                        )
                        st.dataframe(
                            df_display,
                            use_container_width=True,
                            hide_index=True,
                        )
                        has_yahoo_data = True
                except Exception:
                    pass

                if not has_yahoo_data:
                    st.info(
                        f"⚡ Yahoo Direct API par '{ticker}' ka Breakdown nahi"
                        " mila. News & Media se Brokerage Updates fetch kiye ja"
                        " rahe hain:"
                    )

                    brokerage_news = fetch_stock_news(
                        f"{clean_symbol}+brokerage+target+rating"
                    )

                    if brokerage_news:
                        for item in brokerage_news[:5]:
                            st.markdown(
                                f"📌 **[{item['title']}]({item['link']})**"
                            )
                            st.caption(f"🗓️ Published: {item['date']}")
                            st.markdown("---")
                    else:
                        st.warning(
                            "Koi halia Brokerage Target Report nahi mili."
                        )

            # TAB 5: NEWS & SENTIMENT
            with tab5:
                st.subheader(f"📰 Recent News Headlines for {clean_symbol}")
                if news_data:
                    col_news, col_ai = st.columns([0.55, 0.45])
                    with col_news:
                        for item in news_data:
                            st.markdown(
                                f"**[{item['title']}]({item['link']})**"
                            )
                            st.caption(f"📅 {item['date']}")
                            st.markdown("---")
                    with col_ai:
                        st.subheader("🧠 AI News Sentiment")
                        if GEMINI_API_KEY:
                            if st.button("Analyze News Sentiment ✨"):
                                with st.spinner("Analyzing news & searching web..."):
                                    sentiment_report = analyze_news_sentiment(
                                        news_data, clean_symbol, GEMINI_API_KEY
                                    )
                                    st.markdown(sentiment_report)
                        else:
                            st.error(
                                "`.env` file me GEMINI_API_KEY set nahi hai."
                            )
                else:
                    st.info("No recent news found.")

            # TAB 6: AI VERDICT
            with tab6:
                st.subheader("🤖 AI Agent Summary & Verdict")
                if GEMINI_API_KEY:
                    if st.button("Generate Complete AI Verdict ✨"):
                        with st.spinner("Performing real-time market research..."):
                            report = get_ai_analysis(
                                ticker,
                                curr_price,
                                target_mean,
                                rec_key,
                                latest_rsi,
                                pe_str,
                                GEMINI_API_KEY,
                            )
                            st.markdown(report)
                else:
                    st.error("`.env` file me GEMINI_API_KEY set nahi hai.")

            # TAB 7: PORTFOLIO TRACKER (Quantity, Buy Price, Live P/L)
            with tab7:
                st.subheader("⭐ My Watchlist & Portfolio Tracker")
                st.caption(
                    "Table me hi Quantity aur Buy Price edit kar sakte ho — P/L"
                    " automatically calculate ho jayega aur save bhi ho jayega."
                )

                if not st.session_state.watchlist:
                    st.info(
                        "Aapki watchlist khali hai. Sidebar se stocks add karein!"
                    )
                else:
                    portfolio_rows = []
                    with st.spinner("Updating Portfolio Prices..."):
                        for w_sym, w_data in st.session_state.watchlist.items():
                            qty = float(w_data.get("quantity", 0.0))
                            buy_price = float(w_data.get("buy_price", 0.0))
                            try:
                                w_stock = yf.Ticker(w_sym)
                                w_info = w_stock.info or {}
                                w_price = float(
                                    w_info.get(
                                        "currentPrice",
                                        w_info.get("regularMarketPrice", 0.0),
                                    )
                                )
                                w_curr = w_info.get("currency", "INR")
                            except Exception:
                                w_price = 0.0
                                w_curr = "INR"

                            investment = qty * buy_price
                            current_value = qty * w_price
                            pnl = current_value - investment
                            pnl_pct = (
                                (pnl / investment * 100) if investment > 0 else 0.0
                            )

                            portfolio_rows.append({
                                "Ticker": w_sym,
                                "Quantity": qty,
                                "Buy Price": buy_price,
                                "Current Price": round(w_price, 2),
                                "Currency": w_curr,
                                "Investment": round(investment, 2),
                                "Current Value": round(current_value, 2),
                                "P/L": round(pnl, 2),
                                "P/L %": round(pnl_pct, 2),
                            })

                    port_df = pd.DataFrame(portfolio_rows)

                    edited_df = st.data_editor(
                        port_df,
                        use_container_width=True,
                        hide_index=True,
                        disabled=[
                            "Ticker",
                            "Current Price",
                            "Currency",
                            "Investment",
                            "Current Value",
                            "P/L",
                            "P/L %",
                        ],
                        column_config={
                            "Quantity": st.column_config.NumberColumn(
                                "Quantity", min_value=0.0, step=1.0
                            ),
                            "Buy Price": st.column_config.NumberColumn(
                                "Buy Price", min_value=0.0, step=1.0
                            ),
                        },
                        key="portfolio_editor",
                    )

                    # Agar user ne table me quantity/buy price edit kiya hai, use save karo
                    changed = False
                    for _, row in edited_df.iterrows():
                        sym = row["Ticker"]
                        new_qty = float(row["Quantity"])
                        new_buy_price = float(row["Buy Price"])
                        old = st.session_state.watchlist.get(sym, {})
                        if (
                            old.get("quantity") != new_qty
                            or old.get("buy_price") != new_buy_price
                        ):
                            st.session_state.watchlist[sym] = {
                                "quantity": new_qty,
                                "buy_price": new_buy_price,
                            }
                            changed = True

                    if changed:
                        save_portfolio(st.session_state.watchlist)
                        st.rerun()

                    st.markdown("---")
                    total_investment = port_df["Investment"].sum()
                    total_current_value = port_df["Current Value"].sum()
                    total_pnl = total_current_value - total_investment
                    total_pnl_pct = (
                        (total_pnl / total_investment * 100)
                        if total_investment > 0
                        else 0.0
                    )

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Total Investment", f"{total_investment:,.2f}")
                    m2.metric("Current Value", f"{total_current_value:,.2f}")
                    m3.metric("Total P/L", f"{total_pnl:,.2f}")
                    m4.metric("Total P/L %", f"{total_pnl_pct:+.2f}%")

            # TAB 8: IPO SUGGESTIONS
            with tab8:
                st.subheader("🆕 IPO Suggestions & Analysis")
                st.caption(
                    "Current open aur upcoming IPOs ke baare me AI se live-searched"
                    " suggestions lo, saath hi recent IPO news bhi dekho."
                )

                col_news, col_ai = st.columns([0.45, 0.55])

                with col_news:
                    st.markdown("### 📰 Recent IPO News")
                    ipo_news = fetch_ipo_news()
                    if ipo_news:
                        for item in ipo_news:
                            st.markdown(
                                f"**[{item['title']}]({item['link']})**"
                            )
                            st.caption(f"📅 {item['date']}")
                            st.markdown("---")
                    else:
                        st.info("Abhi IPO news load nahi ho payi.")

                with col_ai:
                    st.markdown("### 🤖 AI IPO Suggestions")
                    risk_profile = st.selectbox(
                        "Your Risk Profile:",
                        options=["Conservative", "Moderate", "Aggressive"],
                        index=1,
                        key="ipo_risk_profile",
                    )
                    if GEMINI_API_KEY:
                        if st.button("Get AI IPO Suggestions ✨"):
                            with st.spinner(
                                "Searching live for open & upcoming IPOs..."
                            ):
                                ipo_report = get_ipo_suggestions(
                                    GEMINI_API_KEY, risk_profile
                                )
                                st.markdown(ipo_report)
                    else:
                        st.error(
                            "`.env` file me GEMINI_API_KEY set nahi hai."
                        )

                st.markdown("---")
                st.caption(
                    "⚠️ Yeh AI-generated research hai, financial advice nahi."
                    " IPO investing me listing loss ka risk bhi hota hai."
                )

            # TAB 9: COMPARE & SUGGEST (Buy this stock or a better alternative?)
            with tab9:
                st.subheader("🆚 Compare & Suggest — Ye Stock Kharidna Chahiye?")
                st.caption(
                    f"'{ticker}' ko doosre similar stocks se compare karo, aur AI se"
                    " suggestion lo ki kaunsa best buy hai."
                )

                auto_peers = get_price_range_peers(ticker, curr_price, currency)
                st.caption(
                    f"🏷️ Price range match: **{currency} {curr_price:.2f}** ke aas-paas"
                    " ke stocks apne aap suggest kar diye gaye hain (same currency"
                    " market se), aap chaho toh edit kar sakte ho."
                )

                compare_input = st.text_input(
                    "Compare with (comma-separated tickers, e.g. TCS.NS, WIPRO.NS, HCLTECH.NS):",
                    value=", ".join(auto_peers),
                    key=f"compare_tickers_input_{ticker}",
                )

                if compare_input.strip():
                    compare_tickers = [
                        t.strip().upper()
                        for t in compare_input.split(",")
                        if t.strip()
                    ]
                    all_compare_tickers = [ticker] + [
                        t for t in compare_tickers if t != ticker
                    ]

                    with st.spinner("Fetching comparison data..."):
                        comparison_rows = [
                            fetch_comparison_data(t) for t in all_compare_tickers
                        ]

                    comp_df = pd.DataFrame(comparison_rows)
                    st.dataframe(
                        comp_df, use_container_width=True, hide_index=True
                    )

                    # --- CHART 1: Normalized Price Performance (last 1 year) ---
                    st.markdown("### 📈 Price Performance Comparison (Last 1 Year)")
                    st.caption(
                        "Sab stocks ko 100 se start karke normalize kiya gaya hai,"
                        " taaki alag-alag price range ke stocks bhi fairly compare"
                        " ho sakein — jo line sabse upar hai usne sabse zyada"
                        " grow kiya hai."
                    )
                    perf_fig = go.Figure()
                    for t in all_compare_tickers:
                        hist_df, _, _ = fetch_stock_data(t)
                        if hist_df is not None and not hist_df.empty:
                            normalized = (
                                hist_df["Close"] / hist_df["Close"].iloc[0]
                            ) * 100
                            perf_fig.add_trace(
                                go.Scatter(
                                    x=hist_df["Date"],
                                    y=normalized,
                                    mode="lines",
                                    name=t,
                                    line=dict(width=2),
                                )
                            )
                    perf_fig.update_layout(
                        template="plotly_dark",
                        height=400,
                        yaxis_title="Normalized Price (Base = 100)",
                        xaxis_title="Date",
                        legend_title="Ticker",
                    )
                    st.plotly_chart(perf_fig, use_container_width=True)

                    # --- CHART 2: P/E & P/B Bar Comparison ---
                    st.markdown("### 📊 Valuation Metrics Comparison (P/E vs P/B)")
                    tickers_list = [r["Ticker"] for r in comparison_rows]
                    pe_values = [
                        r["P/E"] if isinstance(r["P/E"], (int, float)) else 0
                        for r in comparison_rows
                    ]
                    pb_values = [
                        r["P/B"] if isinstance(r["P/B"], (int, float)) else 0
                        for r in comparison_rows
                    ]
                    metric_fig = go.Figure()
                    metric_fig.add_trace(
                        go.Bar(x=tickers_list, y=pe_values, name="P/E Ratio")
                    )
                    metric_fig.add_trace(
                        go.Bar(x=tickers_list, y=pb_values, name="P/B Ratio")
                    )
                    metric_fig.update_layout(
                        barmode="group",
                        template="plotly_dark",
                        height=400,
                        yaxis_title="Ratio Value",
                    )
                    st.plotly_chart(metric_fig, use_container_width=True)

                    st.markdown("---")

                    if GEMINI_API_KEY:
                        if st.button(
                            "Get AI Buy Suggestion 🚀", key="compare_ai_btn"
                        ):
                            with st.spinner(
                                "Comparing stocks & searching live news..."
                            ):
                                suggestion = get_comparison_suggestion(
                                    ticker, comparison_rows, GEMINI_API_KEY
                                )
                                st.markdown("### 🤖 AI Suggestion")
                                st.markdown(suggestion)
                    else:
                        st.error(
                            "`.env` file me GEMINI_API_KEY set nahi hai."
                        )
                else:
                    st.info(
                        f"👆 Upar box me un stocks ke tickers daalo jinse aap"
                        f" '{ticker}' ko compare karna chahte ho (comma se"
                        " separate karke). Jaise agar RELIANCE lene ka soch rahe"
                        " ho, toh 'ONGC.NS, IOC.NS' daal ke compare karo."
                    )
