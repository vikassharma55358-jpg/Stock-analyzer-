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

# ----------------- PORTFOLIO PERSISTENCE -----------------
PORTFOLIO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio_data.json")

def load_portfolio():
    try:
        if os.path.exists(PORTFOLIO_FILE):
            with open(PORTFOLIO_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "RELIANCE.NS": {"quantity": 0.0, "buy_price": 0.0},
        "TATAMOTORS.NS": {"quantity": 0.0, "buy_price": 0.0},
        "SJVN.NS": {"quantity": 0.0, "buy_price": 0.0},
        "AAPL": {"quantity": 0.0, "buy_price": 0.0},
    }

def save_portfolio(data):
    try:
        with open(PORTFOLIO_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_portfolio()

st.title("📈 AI Stock, News & Smart Entry Evaluator")

# ----------------- LIVE SCROLLING TICKER TAPE (OPTIMIZED) -----------------
@st.cache_data(ttl=600)
def get_ticker_tape_data(symbols):
    rows = []
    if not symbols:
        return rows
    try:
        tickers = yf.Tickers(" ".join(symbols))
        for sym in symbols:
            try:
                t_info = tickers.tickers[sym].info or {}
                price = t_info.get("currentPrice", t_info.get("regularMarketPrice"))
                prev = t_info.get("previousClose", price)
                if isinstance(price, (int, float)) and isinstance(prev, (int, float)) and prev != 0:
                    pct = (price - prev) / prev * 100
                else:
                    pct = 0.0
                rows.append((sym, price, pct))
            except Exception:
                continue
    except Exception:
        pass
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

SECTOR_PEERS = {
    "technology": ["TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS"],
    "banking": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS"],
    "automobile": ["TATAMOTORS.NS", "MARUTI.NS", "M&M.NS", "HEROMOTOCO.NS"],
    "energy": ["RELIANCE.NS", "ONGC.NS", "IOC.NS", "BPCL.NS"],
    "basic materials": ["TATASTEEL.NS", "HINDALCO.NS", "JSWSTEEL.NS", "HINDCOPPER.NS"],
}

DEFAULT_PEERS = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS"]

def get_auto_peers(symbol, sector, industry):
    key_source = f"{sector or ''} {industry or ''}".lower()
    for key, peers in SECTOR_PEERS.items():
        if key in key_source:
            filtered = [p for p in peers if p != symbol]
            if filtered:
                return filtered[:3]
    return [p for p in DEFAULT_PEERS if p != symbol][:3]

NAME_TICKER_FALLBACK = {
    **POPULAR_STOCKS,
    "Wipro": "WIPRO.NS",
    "Tech Mahindra": "TECHM.NS",
    "Larsen & Toubro": "LT.NS",
    "Axis Bank": "AXISBANK.NS",
    "Maruti Suzuki": "MARUTI.NS",
    "ITC": "ITC.NS",
    "Zomato": "ZOMATO.NS",
    "Google (Alphabet)": "GOOGL",
    "Amazon": "AMZN",
}

@st.cache_data(ttl=1800)
def search_stock_by_name(query):
    if not query or len(query.strip()) < 2:
        return [], None
    results = []
    error = None

    try:
        search_result = yf.Search(query, max_results=5, timeout=5)
        for quote in search_result.quotes:
            symbol = quote.get("symbol")
            name = quote.get("shortname") or quote.get("longname") or symbol
            if symbol:
                results.append({"symbol": symbol, "name": name})
    except Exception as e:
        error = str(e)

    if not results:
        q = query.strip().lower()
        for name, symbol in NAME_TICKER_FALLBACK.items():
            if q in name.lower():
                results.append({"symbol": symbol, "name": name})

    return results, error

# ----------------- SIDEBAR -----------------
st.sidebar.header("🔍 Stock Finder")

name_query = st.sidebar.text_input(
    "Search by Company Name:",
    value="",
    key="name_search_box",
    placeholder="e.g. Tesla, Reliance, Apple",
)

selected_from_search = None
if name_query.strip():
    matches, search_error = search_stock_by_name(name_query)
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
    elif search_error:
        st.sidebar.warning("⚠️ Live search temporarily rate limited. Use Ticker input below.")

selected_company = st.sidebar.selectbox(
    "Or select Popular Stocks:",
    options=["-- Select Stock --"] + list(POPULAR_STOCKS.keys()),
)

manual_ticker = st.sidebar.text_input(
    "OR Enter Ticker Symbol:",
    value="",
    placeholder="e.g. NHPC.NS",
).strip().upper()

if manual_ticker:
    ticker = manual_ticker
elif selected_from_search:
    ticker = selected_from_search
elif selected_company != "-- Select Stock --":
    ticker = POPULAR_STOCKS[selected_company]
else:
    ticker = "RELIANCE.NS"

st.sidebar.caption("💡 Indian stocks ke aage `.NS` zaroor lagayein.")

# --- PORTFOLIO MANAGER ---
st.sidebar.markdown("---")
st.sidebar.subheader("⭐ Portfolio Manager")
add_qty = st.sidebar.number_input("Quantity", min_value=0.0, value=1.0, step=1.0, key="add_qty")
add_buy_price = st.sidebar.number_input(f"Buy Price ({ticker}):", min_value=0.0, value=0.0, step=1.0, key="add_buy_price")

if st.sidebar.button(f"➕ Add '{ticker}' to Portfolio"):
    st.session_state.watchlist[ticker] = {"quantity": add_qty, "buy_price": add_buy_price}
    save_portfolio(st.session_state.watchlist)
    st.sidebar.success(f"Added {ticker}!")
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

# ----------------- CACHED DATA FETCHERS -----------------
def format_market_cap(val, symbol):
    if val == "N/A" or not isinstance(val, (int, float)):
        return "N/A"
    if val >= 1e12:
        return f"₹{val / 1e12:.2f} Lakh Cr" if "NS" in symbol else f"${val / 1e12:.2f}T"
    elif val >= 1e7 and "NS" in symbol:
        return f"₹{val / 1e7:.2f} Cr"
    elif val >= 1e9:
        return f"${val / 1e9:.2f}B"
    return f"{val}"

@st.cache_data(ttl=900)
def fetch_stock_data(symbol):
    try:
        stock = yf.Ticker(symbol)
        df = stock.history(period="1y")

        if df.empty:
            return None, {}, {}

        df = df.reset_index()

        # Indicators
        df["SMA_50"] = df["Close"].rolling(window=50).mean()
        df["SMA_200"] = df["Close"].rolling(window=200).mean()

        delta = df["Close"].diff()
        gain = delta.clip(lower=0).rolling(window=14).mean()
        loss = (-delta.clip(upper=0)).rolling(window=14).mean()
        rs = gain / loss.replace(0, 1e-10)
        df["RSI_14"] = 100 - (100 / (1 + rs))

        df["BB_Middle"] = df["Close"].rolling(window=20).mean()
        df["BB_Std"] = df["Close"].rolling(window=20).std()
        df["BB_Upper"] = df["BB_Middle"] + (df["BB_Std"] * 2)
        df["BB_Lower"] = df["BB_Middle"] - (df["BB_Std"] * 2)

        exp1 = df["Close"].ewm(span=12, adjust=False).mean()
        exp2 = df["Close"].ewm(span=26, adjust=False).mean()
        df["MACD"] = exp1 - exp2
        df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
        df["MACD_Hist"] = df["MACD"] - df["MACD_Signal"]

        info = {}
        try:
            info = stock.info or {}
        except Exception:
            pass

        meta = {
            "regularMarketPrice": info.get("currentPrice", float(df["Close"].iloc[-1])),
            "chartPreviousClose": info.get(
                "previousClose",
                float(df["Close"].iloc[-2]) if len(df) > 1 else float(df["Close"].iloc[-1]),
            ),
            "currency": info.get("currency", "INR" if symbol.endswith(".NS") else "USD"),
        }

        return df, meta, info
    except Exception as e:
        if "Too Many Requests" in str(e):
            st.error("🚨 Yahoo Finance Rate Limit! Thodi der baad retry karein.")
        else:
            st.error(f"Error loading stock data: {e}")
        return None, {}, {}

@st.cache_data(ttl=1200)
def fetch_stock_news(search_term):
    url = f"https://news.google.com/rss/search?q={search_term}+stock+news&hl=en-IN&gl=IN&ceid=IN:en"
    headers = {"User-Agent": "Mozilla/5.0"}
    news_items = []
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item")[:5]:
                news_items.append({
                    "title": item.find("title").text if item.find("title") is not None else "",
                    "link": item.find("link").text if item.find("link") is not None else "",
                    "date": item.find("pubDate").text if item.find("pubDate") is not None else ""
                })
    except Exception:
        pass
    return news_items

@st.cache_data(ttl=900)
def fetch_comparison_data(symbol):
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
            "Ticker": symbol, "Price": "N/A", "P/E": "N/A", "P/B": "N/A",
            "Target Price": "N/A", "Recommendation": "N/A", "Market Cap": "N/A", "Currency": "N/A"
        }

# ----------------- AI GENERATORS -----------------
def get_ai_analysis(ticker_sym, curr_price, target_mean, rec_key, rsi, pe, key):
    try:
        client = genai.Client(api_key=key)
        prompt = f"""
        Act as a top stock analyst. Analyze '{ticker_sym}'.
        - Current Price: {curr_price}
        - Target Price: {target_mean}
        - Consensus Rating: {rec_key}
        - RSI: {rsi}
        - P/E: {pe}

        Provide a concise research report in Hinglish:
        1. Verdict (BUY / HOLD / SELL)
        2. Valuation check (P/E & RSI)
        3. Key Catalysts / Market Factors
        4. Target & Key Risks.
        """
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt
        )
        return response.text
    except Exception as e:
        return f"AI Generation Error: {e}"

# ----------------- MAIN UI -----------------
analyze_btn = st.sidebar.button("Analyze Stock 🚀")

if analyze_btn or ticker:
    with st.spinner(f"Fetching Data for {ticker}..."):
        df, meta, info = fetch_stock_data(ticker)
        clean_symbol = ticker.replace(".NS", "")
        news_data = fetch_stock_news(clean_symbol)

        if df is None or df.empty:
            st.error(f"'{ticker}' ka Data nahi mila ya Rate Limit hitting issue hai. Please wait/check symbol.")
        else:
            curr_price = float(meta.get("regularMarketPrice", df["Close"].iloc[-1]))
            prev_close = float(meta.get("chartPreviousClose", curr_price))

            change = curr_price - prev_close
            pct_change = (change / prev_close * 100) if prev_close != 0 else 0
            currency = meta.get("currency", "INR")

            mcap_raw = info.get("marketCap", "N/A")
            mcap_str = format_market_cap(mcap_raw, ticker)

            pe_ratio = info.get("trailingPE", info.get("forwardPE", "N/A"))
            pe_str = f"{pe_ratio:.2f}" if isinstance(pe_ratio, (int, float)) else "N/A"

            raw_target = info.get("targetMeanPrice", "N/A")
            target_mean = float(raw_target) if isinstance(raw_target, (int, float)) else "N/A"
            rec_key = str(info.get("recommendationKey", "N/A")).upper()

            latest_rsi = f"{df['RSI_14'].iloc[-1]:.1f}" if not pd.isna(df["RSI_14"].iloc[-1]) else "N/A"

            company_name = info.get("longName") or info.get("shortName") or ticker
            st.markdown(f"### {company_name} `{ticker}`")

            # KPI CARDS WITH FULL PARAMETERS
            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("Current Price", f"{curr_price:,.2f} {currency}", f"{pct_change:.2f}%")
            c2.metric("Market Cap", mcap_str)
            c3.metric("P/E Ratio", pe_str)
            c4.metric("RSI (14D)", latest_rsi)
            c5.metric("Analyst Target", f"{target_mean}" if target_mean != "N/A" else "N/A")
            c6.metric("Consensus", rec_key)

            # TABS STRUCTURE
            tab_chart, tab_ai, tab_peers, tab_news = st.tabs(["📊 Interactive Chart", "🤖 AI Research", "⚔️ Peer Comparison", "📰 News"])

            with tab_chart:
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
                fig.add_trace(go.Candlestick(x=df['Date'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Price"), row=1, col=1)
                fig.add_trace(go.Scatter(x=df['Date'], y=df['SMA_50'], name="SMA 50", line=dict(color='yellow', width=1)), row=1, col=1)
                fig.add_trace(go.Scatter(x=df['Date'], y=df['SMA_200'], name="SMA 200", line=dict(color='blue', width=1)), row=1, col=1)
                fig.add_trace(go.Bar(x=df['Date'], y=df['Volume'], name="Volume"), row=2, col=1)
                fig.update_layout(template="plotly_dark", height=500, margin=dict(l=10, r=10, t=20, b=10))
                st.plotly_chart(fig, use_container_width=True)

            with tab_ai:
                if st.button("Generate AI Research Report 📑"):
                    if GEMINI_API_KEY:
                        ai_report = get_ai_analysis(ticker, curr_price, target_mean, rec_key, latest_rsi, pe_str, GEMINI_API_KEY)
                        st.markdown(ai_report)
                    else:
                        st.warning("Please configure your GEMINI_API_KEY in .env file.")

            with tab_peers:
                sector = info.get("sector", "")
                industry = info.get("industry", "")
                auto_peers = get_auto_peers(ticker, sector, industry)
                peer_data = [fetch_comparison_data(p) for p in auto_peers]
                peer_data.insert(0, fetch_comparison_data(ticker))
                st.dataframe(pd.DataFrame(peer_data), hide_index=True, use_container_width=True)

            with tab_news:
                if news_data:
                    for item in news_data:
                        st.markdown(f"**[{item['title']}]({item['link']})**")
                        st.caption(f"Published: {item['date']}")
                else:
                    st.info("No recent news found.")
