import os
from dotenv import load_dotenv
import google.genai as genai
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# Load environment variables for local development
load_dotenv()

# Configure Gemini API key securely from Streamlit Secrets or Environment Variables
if "GEMINI_API_KEY" in st.secrets:
  GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
else:
  GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Initialize Gemini Client
if GEMINI_API_KEY:
  client = genai.Client(api_key=GEMINI_API_KEY)
else:
  client = None

# --- Page Configuration ---
st.set_page_config(
    page_title="Stock Analyzer & AI Evaluator", page_icon="📈", layout="wide"
)

st.title("📈 Stock Analyzer Dashboard & AI Advisor")
st.markdown(
    "Analyze stock fundamentals, technical indicators, news sentiment, and"
    " get AI-powered verdicts."
)

# --- Sidebar Inputs ---
st.sidebar.header("🔍 Stock Configuration")
ticker_input = st.sidebar.text_input(
    "Enter Stock Ticker (e.g., RELIANCE.NS, TCS.NS, AAPL)",
    value="RELIANCE.NS",
)
stock_symbol = ticker_input.strip().upper()

# --- Fetch Stock Data ---
@st.cache_data(ttl=3600)
def load_stock_data(symbol):
  try:
    stock = yf.Ticker(symbol)
    df = stock.history(period="6mo")
    info = stock.info
    return stock, df, info
  except Exception as e:
    return None, pd.DataFrame(), {}


stock_obj, hist_df, stock_info = load_stock_data(stock_symbol)

# --- Navigation Tabs ---
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "💡 Buy/Sell Evaluator",
    "📊 Price & Technicals",
    "🏛️ Company Fundamentals",
    "🎯 Brokerage Targets",
    "📰 News & Sentiment",
    "🤖 AI Financial Verdict",
    "⭐ My Watchlist",
])

# ==========================================
# TAB 1: Buy/Sell Evaluator
# ==========================================
with tab1:
  st.subheader("💡 Buy / Sell Evaluator")
  if not hist_df.empty:
    current_price = hist_df["Close"].iloc[-1]
    st.metric(
        label=f"Current Price for {stock_symbol}",
        value=f"INR {current_price:,.2f}",
    )

    col1, col2 = st.columns(2)
    with col1:
      target_buy = st.number_input("Your Target Buy Price (INR)", value=float(current_price * 0.95))
    with col2:
      target_sell = st.number_input("Your Target Sell Price (INR)", value=float(current_price * 1.10))

    if st.button("Evaluate Entry/Exit"):
      if current_price <= target_buy:
        st.success(
            "🟢 **Good Time to Buy!** Current price is at or below your target"
            " buy price."
        )
      elif current_price >= target_sell:
        st.warning(
            "🔴 **Consider Selling / Book Profits!** Price has reached your"
            " target sell level."
        )
      else:
        st.info(
            "🟡 **Hold / Wait.** Current price is fluctuating between your buy"
            " and sell targets."
        )
  else:
    st.error("Could not fetch price data for the entered ticker symbol.")

# ==========================================
# TAB 2: Price & Technicals
# ==========================================
with tab2:
  st.subheader("📊 Price Chart & Technical Indicators")
  if not hist_df.empty:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=hist_df.index,
            y=hist_df["Close"],
            mode="lines",
            name="Close Price",
            line=dict(color="blue", width=2),
        )
    )
    fig.update_layout(
        title=f"{stock_symbol} 6-Month Price Trend",
        xaxis_title="Date",
        yaxis_title="Price (INR)",
        template="plotly_dark",
    )
    st.plotly_chart(fig, use_container_width=True)
  else:
    st.warning("No historical chart data available.")

# ==========================================
# TAB 3: Company Fundamentals (FIXED N/A)
# ==========================================
with tab3:
  st.subheader("🏛️ Key Fundamental Metrics")
  if stock_info:
    # Safe data extraction to eliminate N/A errors
    raw_mcap = stock_info.get("marketCap") or stock_info.get("enterpriseValue")
    if raw_mcap:
      market_cap = f"₹ {raw_mcap / 10000000:,.2f} Cr"
    else:
      market_cap = "N/A"

    raw_pe = stock_info.get("trailingPE") or stock_info.get("forwardPE")
    pe_ratio = round(float(raw_pe), 2) if raw_pe else "N/A"

    high_52 = stock_info.get("fiftyTwoWeekHigh")
    high_52_str = f"INR {high_52:,.2f}" if high_52 else "N/A"

    low_52 = stock_info.get("fiftyTwoWeekLow")
    low_52_str = f"INR {low_52:,.2f}" if low_52 else "N/A"

    col1, col2, col3 = st.columns(3)
    with col1:
      st.metric(label="Market Capitalization", value=market_cap)
      st.metric(label="P/E Ratio", value=pe_ratio)
    with col2:
      st.metric(label="52-Week High", value=high_52_str)
      st.metric(label="52-Week Low", value=low_52_str)
    with col3:
      div_yield = stock_info.get("dividendYield")
      div_yield_str = (
          f"{float(div_yield) * 100:.2f}%" if div_yield else "N/A"
      )
      st.metric(label="Dividend Yield", value=div_yield_str)
  else:
    st.warning(
        "Fundamental data is currently unavailable for this specific ticker."
    )

# ==========================================
# TAB 4: Brokerage Targets
# ==========================================
with tab4:
  st.subheader("🎯 Brokerage Targets & Recommendations")
  target_mean = stock_info.get("targetMeanPrice")
  recommendation = stock_info.get("recommendationKey")

  if target_mean:
    st.metric(label="Analyst Consensus Mean Target", value=f"INR {target_mean:,.2f}")
  else:
    st.info("Analyst consensus target price not available.")

  if recommendation:
    st.info(f"**Brokerage Consensus Rating:** `{recommendation.upper()}`")
  else:
    st.info("No active brokerage recommendations found.")

# ==========================================
# TAB 5: News & Sentiment
# ==========================================
with tab5:
  st.subheader("📰 Recent News Headlines & AI Sentiment")
  try:
    news_list = stock_obj.news if stock_obj else []
  except Exception:
    news_list = []

  if news_list:
    for item in news_list[:5]:
      title = item.get("title", "No Title")
      publisher = item.get("publisher", "Unknown Source")
      link = item.get("link", "#")
      st.markdown(f"- [{title}]({link}) — *{publisher}*")

    if st.button("Analyze News Sentiment ✨"):
      if client:
        with st.spinner("Analyzing sentiment with Gemini AI..."):
          headlines_text = "\n".join(
              [n.get("title", "") for n in news_list[:5]]
          )
          prompt = (
              "Analyze the market sentiment (Bullish, Bearish, or Neutral) for"
              f" these headlines:\n{headlines_text}"
          )
          response = client.models.generate_content(
              model="gemini-2.5-flash", contents=prompt
          )
          st.success("### AI News Sentiment Report")
          st.write(response.text)
      else:
        st.error("Gemini API Key is missing or invalid.")
  else:
    st.info("No recent news found for this ticker.")

# ==========================================
# TAB 6: AI Financial Verdict
# ==========================================
with tab6:
  st.subheader("🤖 Comprehensive AI Financial Verdict")
  if st.button("Generate Complete AI Verdict 🚀"):
    if client:
      with st.spinner("Synthesizing stock metrics and generating AI verdict..."):
        prompt = (
            f"Provide a comprehensive financial verdict for stock {stock_symbol}"
            f" with current price data, fundamentals summary, and risk analysis."
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt
        )
        st.markdown(response.text)
    else:
      st.error("Gemini API Client is not configured properly.")

# ==========================================
# TAB 7: My Watchlist
# ==========================================
with tab7:
  st.subheader("⭐ My Watchlist")
  if "watchlist" not in st.session_state:
    st.session_state["watchlist"] = ["RELIANCE.NS", "TCS.NS", "INFY.NS"]

  new_stock = st.text_input("Add Ticker to Watchlist")
  if st.button("Add to Watchlist"):
    if new_stock and new_stock.upper() not in st.session_state["watchlist"]:
      st.session_state["watchlist"].append(new_stock.upper())
      st.success(f"Added {new_stock.upper()} to watchlist!")

  st.write("**Current Tracked Stocks:**")
  for item in st.session_state["watchlist"]:
    st.markdown(f"- 📊 `{item}`")
