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

# Initialize Watchlist in Session State
if "watchlist" not in st.session_state:
    st.session_state.watchlist = [
        "RELIANCE.NS",
        "TATAMOTORS.NS",
        "SJVN.NS",
        "AAPL",
    ]

st.title("📈 AI Stock, News & Smart Entry Evaluator")

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

# ----------------- SIDEBAR -----------------
st.sidebar.header("🔍 Quick Stock Finder")

selected_company = st.sidebar.selectbox(
    "Select a Popular Stock:",
    options=["Custom Input"] + list(POPULAR_STOCKS.keys()),
)

default_ticker = (
    POPULAR_STOCKS[selected_company]
    if selected_company != "Custom Input"
    else "RELIANCE.NS"
)

ticker = (
    st.sidebar.text_input("Or Enter Ticker Symbol Manually:", value=default_ticker)
    .strip()
    .upper()
)

st.sidebar.markdown("---")
st.sidebar.subheader("📌 Common Stock Symbols")
ref_df = pd.DataFrame(
    list(POPULAR_STOCKS.items()), columns=["Company Name", "Symbol"]
)
st.sidebar.dataframe(ref_df, hide_index=True, use_container_width=True)

# --- WATCHLIST MANAGER ---
st.sidebar.markdown("---")
st.sidebar.subheader("⭐ Watchlist Manager")

if st.sidebar.button(f"➕ Add '{ticker}' to Watchlist"):
    if ticker not in st.session_state.watchlist:
        st.session_state.watchlist.append(ticker)
        st.sidebar.success(f"Added {ticker}!")
        st.rerun()
    else:
        st.sidebar.info(f"{ticker} is already in Watchlist.")

if st.session_state.watchlist:
    selected_to_remove = st.sidebar.selectbox(
        "Remove Stock:",
        options=["Select Stock"] + st.session_state.watchlist,
        key="remove_stock_select",
    )
    if selected_to_remove != "Select Stock":
        if st.sidebar.button(f"❌ Remove {selected_to_remove}"):
            st.session_state.watchlist.remove(selected_to_remove)
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


# ----------------- AI GENERATORS -----------------
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
        
        Answer clearly in simple Hinglish (mix of Hindi + English):
        1. **Verdict**: Should the user buy at {user_price}? (GOOD ENTRY / RISKY / WAIT FOR DIP)
        2. **Risk to Reward Ratio**: Evaluate if buying at {user_price} leaves enough profit upside compared to the Brokerage Target ({target_mean}).
        3. **Suggested Entry Zone & Stop Loss**: Give a clear suggested buying range and strict stop-loss price.
        Keep it direct and actionable with bullet points.
        """
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt
        )
        return response.text
    except Exception as e:
        return f"AI Evaluation Error: {e}"


def analyze_news_sentiment(news_list, key):
    try:
        client = genai.Client(api_key=key)
        headlines = "\n".join([f"- {n['title']}" for n in news_list])
        prompt = f"""
        Analyze these recent news headlines for a stock:
        {headlines}
        
        Provide a response in simple Hinglish:
        1. Overall News Sentiment: (BULLISH 🟢 / BEARISH 🔴 / NEUTRAL 🟡)
        2. Key Market Catalysts or Deals mentioned.
        3. Short-term price impact.
        """
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt
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
        
        Provide a research report in Hinglish:
        1. Verdict (BUY / HOLD / SELL)
        2. Valuation check (P/E & RSI)
        3. Target & Key Risks.
        """
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt
        )
        return response.text
    except Exception as e:
        return f"AI Generation Error: {e}"


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

            tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
                "💡 Buy/Sell Evaluator",
                "📊 Price & Technicals",
                "🏛️ Company Fundamentals",
                "🎯 Brokerage Targets",
                "📰 News & Sentiment",
                "🤖 AI Financial Verdict",
                "⭐ My Watchlist",
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
                                "Analyzing risk/reward ratio for your price..."
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

                # 1. Try Yahoo Finance Data First
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

                # 2. Fallback: Search Specific Brokerage Targets via News
                if not has_yahoo_data:
                    st.info(
                        f"⚡ Yahoo Direct API par '{ticker}' ka Breakdown नहीं"
                        " मिला। News & Media से Brokerage Updates fetch किए जा"
                        " रहे हैं:"
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
                            "कोई हालिया Brokerage Target Report नहीं मिली।"
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
                                with st.spinner("Analyzing news..."):
                                    sentiment_report = analyze_news_sentiment(
                                        news_data, GEMINI_API_KEY
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

            # TAB 7: WATCHLIST TRACKER
            with tab7:
                st.subheader("⭐ Your Personal Watchlist Tracker")
                st.caption(
                    "Real-time tracking for your favorite stocks in this"
                    " session."
                )

                if not st.session_state.watchlist:
                    st.info(
                        "Aapki watchlist khali hai. Sidebar se stocks add"
                        " karein!"
                    )
                else:
                    watchlist_data = []
                    with st.spinner("Updating Watchlist Prices..."):
                        for item in st.session_state.watchlist:
                            w_df, w_meta, _ = fetch_stock_data(item)
                            if w_df is not None and not w_df.empty:
                                w_curr = float(
                                    w_meta.get(
                                        "regularMarketPrice",
                                        w_df["Close"].iloc[-1],
                                    )
                                )
                                w_prev = float(
                                    w_meta.get("chartPreviousClose", w_curr)
                                )
                                w_change = w_curr - w_prev
                                w_pct = (
                                    (w_change / w_prev * 100)
                                    if w_prev != 0
                                    else 0
                                )

                                sma_50_val = w_df["SMA_50"].iloc[-1] if "SMA_50" in w_df.columns and not pd.isna(w_df["SMA_50"].iloc[-1]) else w_curr

                                watchlist_data.append({
                                    "Symbol": item,
                                    "Price": (
                                        f"{w_meta.get('currency', 'INR')}"
                                        f" {w_curr:.2f}"
                                    ),
                                    "Day Change": f"{w_change:+.2f}",
                                    "Change (%)": f"{w_pct:+.2f}%",
                                    "50-SMA Status": (
                                        "Bullish 🟢"
                                        if w_curr > sma_50_val
                                        else "Bearish 🔴"
                                    ),
                                })

                    if watchlist_data:
                        w_df_display = pd.DataFrame(watchlist_data)
                        st.dataframe(
                            w_df_display,
                            use_container_width=True,
                            hide_index=True,
                        )

                        st.markdown("---")
                        st.markdown("### 📊 Watchlist Live Summary Cards")
                        cols = st.columns(min(len(watchlist_data), 4))
                        for idx, stock in enumerate(watchlist_data[:4]):
                            with cols[idx]:
                                st.metric(
                                    label=stock["Symbol"],
                                    value=stock["Price"],
                                    delta=f"{stock['Change (%)']}",
                                )
