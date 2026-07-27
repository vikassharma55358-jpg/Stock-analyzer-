import datetime
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# ----------------- PAGE CONFIG -----------------
st.set_page_config(
    page_title="Indian Stock Market AI Dashboard",
    page_icon="📈",
    layout="wide",
)

# ----------------- POPULAR TICKERS DICTIONARY -----------------
# Easy search and suggestions for popular Indian stocks & commodities
POPULAR_STOCKS = {
    "SJVN Limited": "SJVN.NS",
    "Hindustan Copper": "HINDCOPPER.NS",
    "Tata Motors": "TATAMOTORS.NS",
    "Reliance Industries": "RELIANCE.NS",
    "State Bank of India (SBI)": "SBIN.NS",
    "Infosys": "INFY.NS",
    "TCS": "TCS.NS",
    "Silver Futures (MCX / US)": "SI=F",
    "Gold Futures": "GC=F",
    "Nifty 50 Index": "^NSEI",
    "Bank Nifty Index": "^NSEBANK",
}

# ----------------- SESSION STATE SETUP -----------------
if "watchlist" not in st.session_state:
    st.session_state["watchlist"] = ["SJVN.NS", "HINDCOPPER.NS", "SI=F"]

# ----------------- HELPER FUNCTIONS -----------------
@st.cache_data(ttl=300)
def fetch_stock_data(ticker_symbol, period="1y", interval="1d"):
    """Fetch market data using yfinance with caching."""
    try:
        stock = yf.Ticker(ticker_symbol)
        df = stock.history(period=period, interval=interval)
        info = stock.info
        return df, info
    except Exception as e:
        st.error(f"Error fetching data for {ticker_symbol}: {e}")
        return pd.DataFrame(), {}


def calculate_rsi(df, window=14):
    """Calculate Relative Strength Index (RSI)."""
    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


# ----------------- SIDEBAR -----------------
st.sidebar.title("🔍 Search & Settings")

# 1. Quick Selector Dropdown (Suggestions)
selected_suggestion = st.sidebar.selectbox(
    "💡 Quick Select Popular Stocks/Indices:",
    options=["Custom Search..."] + list(POPULAR_STOCKS.keys()),
)

# 2. Dynamic Ticker Symbol Logic with Suggestions
if selected_suggestion != "Custom Search...":
    default_ticker = POPULAR_STOCKS[selected_suggestion]
else:
    default_ticker = "SJVN.NS"

ticker_input = st.sidebar.text_input(
    "Enter Yahoo Finance Ticker Symbol:",
    value=default_ticker,
    help="e.g., SJVN.NS, HINDCOPPER.NS, RELIANCE.NS, SI=F (Silver)",
).upper()

# Time Period Selection
period_option = st.sidebar.selectbox(
    "Select Time Period:",
    options=["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"],
    index=3,
)

# Add to Watchlist Button
if st.sidebar.button("⭐ Add to Watchlist"):
    if ticker_input not in st.session_state["watchlist"]:
        st.session_state["watchlist"].append(ticker_input)
        st.sidebar.success(f"Added {ticker_input} to Watchlist!")
    else:
        st.sidebar.info(f"{ticker_input} is already in Watchlist.")

# ----------------- MAIN CONTENT -----------------
st.title("📈 Indian Stock Market & Commodity AI Dashboard")

if ticker_input:
    df, info = fetch_stock_data(ticker_input, period=period_option)

    if not df.empty:
        # Calculate Indicators
        df["MA20"] = df["Close"].rolling(window=20).mean()
        df["MA50"] = df["Close"].rolling(window=50).mean()
        df["RSI"] = calculate_rsi(df)

        company_name = info.get("longName", ticker_input)
        current_price = df["Close"].iloc[-1]
        prev_close = df["Close"].iloc[-2] if len(df) > 1 else current_price
        price_change = current_price - prev_close
        pct_change = (price_change / prev_close) * 100

        # Header Metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Stock Symbol", ticker_input)
        col2.metric("Current Price", f"₹{current_price:.2f}" if ".NS" in ticker_input else f"${current_price:.2f}")
        col3.metric("Daily Change", f"{price_change:+.2f}", f"{pct_change:+.2f}%")
        col4.metric("Latest RSI (14)", f"{df['RSI'].iloc[-1]:.2f}" if not pd.isna(df['RSI'].iloc[-1]) else "N/A")

        st.markdown("---")

        # TABS INTERFACE
        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
            "📊 Candlestick Chart", 
            "📈 Technical Indicators", 
            "📋 Company Profile", 
            "📊 Financials", 
            "🤖 AI Market Insights", 
            "🎯 Delivery & OI Analysis",
            "⭐ Watchlist Tracker"
        ])

        # TAB 1: CANDLESTICK CHART
        with tab1:
            st.subheader(f"Price Chart - {company_name}")
            fig = go.Figure()
            fig.add_trace(go.Candlestick(
                x=df.index,
                open=df['Open'],
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                name='Market Price'
            ))
            fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange', width=1.5), name='20 SMA'))
            fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], line=dict(color='blue', width=1.5), name='50 SMA'))
            fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=500)
            st.plotly_chart(fig, use_container_width=True)

        # TAB 2: TECHNICAL INDICATORS
        with tab2:
            st.subheader("Technical Indicator Overview")
            
            # RSI Chart
            rsi_fig = go.Figure()
            rsi_fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple', width=2), name='RSI'))
            rsi_fig.add_hline(y=70, line_dash="dash", line_color="red", annotation_text="Overbought (70)")
            rsi_fig.add_hline(y=30, line_dash="dash", line_color="green", annotation_text="Oversold (30)")
            rsi_fig.update_layout(template="plotly_dark", height=300, title="RSI (Relative Strength Index)")
            st.plotly_chart(rsi_fig, use_container_width=True)

            # Volume Chart
            vol_fig = go.Figure()
            vol_fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name='Trading Volume', marker_color='teal'))
            vol_fig.update_layout(template="plotly_dark", height=300, title="Daily Trading Volume")
            st.plotly_chart(vol_fig, use_container_width=True)

        # TAB 3: COMPANY PROFILE
        with tab3:
            st.subheader("Company Overview & Key Metrics")
            st.write(f"**Business Summary:** {info.get('longBusinessSummary', 'Information not available.')}")
            
            p_col1, p_col2, p_col3 = st.columns(3)
            p_col1.write(f"**Sector:** {info.get('sector', 'N/A')}")
            p_col1.write(f"**Industry:** {info.get('industry', 'N/A')}")
            p_col2.write(f"**Market Cap:** {info.get('marketCap', 'N/A')}")
            p_col2.write(f"**PE Ratio:** {info.get('trailingPE', 'N/A')}")
            p_col3.write(f"**52 Week High:** {info.get('fiftyTwoWeekHigh', 'N/A')}")
            p_col3.write(f"**52 Week Low:** {info.get('fiftyTwoWeekLow', 'N/A')}")

        # TAB 4: FINANCIALS
        with tab4:
            st.subheader("Historical Price & Volume Raw Data")
            st.dataframe(df.tail(30).sort_index(ascending=False), use_container_width=True)

        # TAB 5: AI MARKET INSIGHTS
        with tab5:
            st.subheader("🤖 Rule-Based AI Technical Summary")
            latest_rsi = df['RSI'].iloc[-1]
            latest_close = df['Close'].iloc[-1]
            latest_ma20 = df['MA20'].iloc[-1]
            latest_ma50 = df['MA50'].iloc[-1]

            rsi_signal = "NEUTRAL"
            if latest_rsi > 70:
                rsi_signal = "OVERBOUGHT 🔴 (Potential Correction)"
            elif latest_rsi < 30:
                rsi_signal = "OVERSOLD 🟢 (Potential Rebound)"
            
            trend_signal = "BULLISH 🟢" if latest_close > latest_ma50 else "BEARISH 🔴"

            st.write(f"**Overall Trend (50 SMA):** {trend_signal}")
            st.write(f"**RSI Momentum Status:** {rsi_signal}")
            st.write(f"**20 SMA Support Level:** {latest_ma20:.2f}")

        # TAB 6: DELIVERY & OI ANALYSIS
        with tab6:
            st.subheader("Derivative & Delivery Insights")
            st.info("Delivery percentage and Open Interest (OI) tracking for NSE Futures & Options.")
            st.write(f"**Ticker:** {ticker_input}")
            st.write("*(Note: Real-time NSE F&O Open Interest data requires direct NSE API connection or brokerage integration.)*")

        # TAB 7: WATCHLIST TRACKER
        with tab7:
            st.subheader("⭐ My Stock & Commodity Watchlist")
            if st.session_state["watchlist"]:
                watchlist_data = []
                for wl_ticker in st.session_state["watchlist"]:
                    w_df, w_info = fetch_stock_data(wl_ticker, period="5d")
                    if not w_df.empty:
                        w_price = w_df["Close"].iloc[-1]
                        w_prev = w_df["Close"].iloc[-2] if len(w_df) > 1 else w_price
                        w_chg = ((w_price - w_prev) / w_prev) * 100
                        watchlist_data.append({
                            "Ticker": wl_ticker,
                            "Price": round(w_price, 2),
                            "1D Change (%)": round(w_chg, 2)
                        })
                st.table(pd.DataFrame(watchlist_data))
            else:
                st.write("Watchlist is currently empty.")

            st.markdown("---")
            if st.button("🔄 Refresh Watchlist Data"):
                st.rerun()

    else:
        st.warning("No data found for the selected ticker. Please double-check the symbol (e.g., SJVN.NS, HINDCOPPER.NS).")

# ----------------- FOOTER -----------------
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: gray;'>"
    "💡 <i>Disclaimer: This app provides AI-assisted stock insights for informational purposes only. "
    "Always consult a qualified financial advisor before making real investment decisions.</i>"
    "</div>",
    unsafe_allow_html=True,
)
