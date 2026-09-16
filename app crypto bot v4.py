import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime, timezone, timedelta
import matplotlib.pyplot as plt

st.set_page_config(page_title="Crypto Bot Simulator", layout="wide")
st.title("🤖 Crypto Trading Bot Simulator - Trend Following V4")
st.markdown("Strategia TREND FOLLOWING PURO - Segue i trend senza TP/SL rigidi")

# Costanti
BASE = "https://api.coinbase.com/api/v3/brokerage/market/products/{product_id}/candles"
TOP_CRYPTOS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD",
    "AVAX-USD", "DOGE-USD", "MATIC-USD", "LTC-USD", "UNI-USD",
    "LINK-USD", "ATOM-USD", "POLKADOT-USD", "SHIB-USD", "TRX-USD",
    "NEAR-USD", "FIL-USD", "PEPE-USD", "BLUR-USD", "BONK-USD"
]

FEE = 0.005

# Sidebar
st.sidebar.header("⚙️ Parametri")
initial_capital = st.sidebar.number_input("Capitale iniziale (€)", value=10.0, min_value=1.0, step=1.0)
days = st.sidebar.number_input("Giorni recenti da ORA", value=30, min_value=7, max_value=90, step=5)
st.sidebar.caption(f"📅 Simula sui dati reali degli ultimi {days} giorni")

st.sidebar.header("💰 Soglie di accantonamento")
threshold1 = st.sidebar.number_input("Soglia 1 (€ profitto)", value=1.0, min_value=0.1, step=0.1)
accantonamento1 = st.sidebar.number_input("Accantona % soglia 1", value=80, min_value=0, max_value=100) / 100

threshold2 = st.sidebar.number_input("Soglia 2 (€ profitto)", value=5.0, min_value=1.0, step=1.0)
accantonamento2 = st.sidebar.number_input("Accantona % soglia 2", value=90, min_value=0, max_value=100) / 100

threshold3 = st.sidebar.number_input("Soglia 3 (€ profitto)", value=10.0, min_value=5.0, step=5.0)
accantonamento3 = st.sidebar.number_input("Accantona % soglia 3", value=95, min_value=0, max_value=100) / 100

st.sidebar.markdown("---")
st.sidebar.info(f"🤖 Bot Trend Following | {len(TOP_CRYPTOS)} crypto | Dati recenti")

def fetch_candles(product, days):
    end = int(time.time())
    start = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    all_candles = []
    step = 350 * 3600
    cur = start
    
    while cur < end:
        nxt = min(cur + step, end)
        params = {"start": str(cur), "end": str(nxt), "granularity": "ONE_HOUR", "limit": 350}
        
        try:
            r = requests.get(BASE.format(product_id=product), params=params, timeout=20)
            if r.status_code != 200:
                return None
            data = r.json().get("candles", [])
            if data:
                all_candles.extend(data)
            cur = nxt
            time.sleep(0.15)
        except:
            return None
    
    if not all_candles:
        return None
    
    df = pd.DataFrame(all_candles)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    
    df["start"] = pd.to_numeric(df["start"], errors="coerce").astype(int)
    df["time"] = pd.to_datetime(df["start"], unit="s", utc=True)
    df = df.sort_values("time")
    df = df.drop_duplicates("start")
    df = df.set_index("time")[["open", "high", "low", "close", "volume"]]
    
    return df

def calculate_indicators(df):
    d = df.copy()
    d["ema20"] = d.close.ewm(span=20, adjust=False).mean()
    d["ema30"] = d.close.ewm(span=30, adjust=False).mean()
    d["ema35"] = d.close.ewm(span=35, adjust=False).mean()
    d["ema38"] = d.close.ewm(span=38, adjust=False).mean()
    d["ema40"] = d.close.ewm(span=40, adjust=False).mean()
    d["ema45"] = d.close.ewm(span=45, adjust=False).mean()
    d["ema50"] = d.close.ewm(span=50, adjust=False).mean()
    d["ema55"] = d.close.ewm(span=55, adjust=False).mean()
    d["ema60"] = d.close.ewm(span=60, adjust=False).mean()
    
    d["ema80"] = d.close.ewm(span=80, adjust=False).mean()
    d["ema100"] = d.close.ewm(span=100, adjust=False).mean()
    d["ema120"] = d.close.ewm(span=120, adjust=False).mean()
    d["ema140"] = d.close.ewm(span=140, adjust=False).mean()
    d["ema150"] = d.close.ewm(span=150, adjust=False).mean()
    d["ema180"] = d.close.ewm(span=180, adjust=False).mean()
    d["ema200"] = d.close.ewm(span=200, adjust=False).mean()
    d["ema220"] = d.close.ewm(span=220, adjust=False).mean()
    d["ema250"] = d.close.ewm(span=250, adjust=False).mean()
    
    d["vol_ma20"] = d.volume.rolling(20).mean()
    return d

def backtest_trend_following(data_dict, initial_capital, threshold1, acc1, threshold2, acc2, threshold3, acc3):
    variants = [
        {"name": "Trend50_200", "fast": 50, "slow": 200},
        {"name": "Trend30_100", "fast": 30, "slow": 100},
        {"name": "Trend40_150", "fast": 40, "slow": 150},
        {"name": "Trend20_50", "fast": 20, "slow": 50},
        {"name": "Trend60_250", "fast": 60, "slow": 250},
        {"name": "Trend35_120", "fast": 35, "slow": 120},
        {"name": "Trend25_80", "fast": 25, "slow": 80},
        {"name": "Trend45_180", "fast": 45, "slow": 180},
        {"name": "Trend55_220", "fast": 55, "slow": 220},
        {"name": "Trend38_140", "fast": 38, "slow": 140},
    ]
    
    results = []
    
    for variant in variants:
        ind_dict = {}
        for crypto, df in data_dict.items():
            if df is not None and len(df) > variant["slow"] + 20:
                ind_dict[crypto] = calculate_indicators(df)
        
        if not ind_dict:
            continue
        
        num_candles = len(list(ind_dict.values())[0])
        trading_capital = initial_capital
        accantonato = 0.0
        position = None
        trades = []
        
        start_idx = variant["slow"] + 20
        
        for i in range(start_idx, num_candles - 1):
            if position is None:
                best_crypto = None
                best_strength = 0
                
                for crypto, ind_df in ind_dict.items():
                    if i < len(ind_df):
                        row = ind_df.iloc[i]
                        price = float(row['close'])
                        fast_ema = float(row[f'ema{variant["fast"]}'])
                        slow_ema = float(row[f'ema{variant["slow"]}'])
                        
                        if price > fast_ema and fast_ema > slow_ema:
                            strength = (price - fast_ema) / fast_ema
                            if strength > best_strength:
                                best_strength = strength
                                best_crypto = crypto
                
                if best_crypto is not None:
                    ind_df = ind_dict[best_crypto]
                    nxt = ind_df.iloc[i + 1]
                    entry_price = float(nxt.open)
                    
                    position = {
                        "crypto": best_crypto,
                        "entry_price": entry_price,
                        "entry_time": ind_df.index[i + 1],
                        "entry_capital": trading_capital,
                    }
            else:
                crypto = position["crypto"]
                ind_df = ind_dict[crypto]
                
                if i + 1 < len(ind_df):
                    nxt = ind_df.iloc[i + 1]
                    price = float(nxt.close)
                    fast_ema = float(nxt[f'ema{variant["fast"]}'])
                    
                    if price < fast_ema:
                        exit_price = float(nxt.close)
                        gross = exit_price / position["entry_price"] - 1
                        net_factor = (1 + gross) * (1 - FEE) * (1 - FEE)
                        new_capital = position["entry_capital"] * net_factor
                        
                        trades.append({"entry": position["entry_price"], "exit": exit_price, "net_pct": (new_capital/position["entry_capital"]-1)*100})
                        
                        trading_capital = new_capital
                        total_capital = trading_capital + accantonato
                        profitto = total_capital - initial_capital
                        
                        if profitto >= threshold3:
                            da_acc = (trading_capital - position["entry_capital"]) * acc3
                            if da_acc > 0:
                                accantonato += da_acc
                                trading_capital -= da_acc
                        elif profitto >= threshold2:
                            da_acc = (trading_capital - position["entry_capital"]) * acc2
                            if da_acc > 0:
                                accantonato += da_acc
                                trading_capital -= da_acc
                        elif profitto >= threshold1:
                            da_acc = (trading_capital - position["entry_capital"]) * acc1
                            if da_acc > 0:
                                accantonato += da_acc
                                trading_capital -= da_acc
                        
                        position = None
        
        total_capital = trading_capital + accantonato
        profitto = total_capital - initial_capital
        profitto_pct = (profitto / initial_capital) * 100
        num_trades = len(trades)
        wins = len([t for t in trades if t["net_pct"] > 0]) if trades else 0
        win_rate = (wins / num_trades * 100) if num_trades > 0 else 0
        
        results.append({
            "variant": variant["name"],
            "fast": variant["fast"],
            "slow": variant["slow"],
            "trades": num_trades,
            "wins": wins,
            "win_rate": win_rate,
            "capital": total_capital,
            "profitto": profitto,
            "profitto_pct": profitto_pct
        })
    
    return results

# Main
st.markdown(f"**Capitale iniziale:** €{initial_capital} | **Dati:** ultimi {days} giorni (reali, da ORA) | **Asset:** TOP {len(TOP_CRYPTOS)} Crypto")

if st.button("▶️ Esegui Trend Following Optimization", key="simulate"):
    st.info(f"⏳ Scaricamento dati da Coinbase per {len(TOP_CRYPTOS)} crypto...")
    
    data_dict = {}
    progress = st.progress(0)
    
    for idx, crypto in enumerate(TOP_CRYPTOS):
        try:
            progress.progress((idx + 1) / len(TOP_CRYPTOS))
            df = fetch_candles(crypto, days)
            if df is not None:
                data_dict[crypto] = df
        except:
            pass
    
    progress.empty()
    
    valid_cryptos = [c for c, df in data_dict.items() if df is not None and len(df) > 250]
    
    if len(valid_cryptos) >= 12:
        st.success(f"✓ Scaricate {len(valid_cryptos)} crypto valide")
        
        st.info("🔍 Trend Following Optimization: testing 10 varianti...")
        with st.spinner("Analisi in corso (1-2 minuti)..."):
            variants_results = backtest_trend_following(data_dict, initial_capital, threshold1, accantonamento1, threshold2, accantonamento2, threshold3, accantonamento3)
        
        if variants_results:
            variants_df = pd.DataFrame(variants_results)
            best_idx = variants_df["profitto_pct"].idxmax()
            best_variant = variants_df.iloc[best_idx]
            
            st.success(f"✅ Migliore variante trovata: **{best_variant['variant']}**")
            
            st.subheader("🏆 Risultato Migliore")
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("💰 Capitale Finale", f"€{best_variant['capital']:.2f}")
            col2.metric("💹 Profitto", f"€{best_variant['profitto']:.2f}")
            col3.metric("📈 +%", f"{best_variant['profitto_pct']:.2f}%")
            col4.metric("📋 N. Trade", int(best_variant['trades']))
            col5.metric("✅ Win Rate", f"{best_variant['win_rate']:.1f}%")
            
            st.markdown(f"**Strategia Ottimale:** EMA Fast {int(best_variant['fast'])} / EMA Slow {int(best_variant['slow'])}")
            
            st.subheader("📊 Confronto Tutte le Varianti")
            display_variants = variants_df[["variant", "fast", "slow", "trades", "win_rate", "profitto", "profitto_pct"]].copy()
            display_variants.columns = ["Strategia", "EMA Fast", "EMA Slow", "Trade", "Win %", "Profitto €", "Profitto %"]
            st.dataframe(display_variants, use_container_width=True)
            
            csv = variants_df.to_csv(index=False)
            st.download_button(label="📥 Scarica Risultati CSV", data=csv, file_name=f"trend_results_{days}d.csv", mime="text/csv")
        else:
            st.error("❌ Errore nel testing")
    else:
        st.error(f"❌ Dati insufficienti: {len(valid_cryptos)}/{len(TOP_CRYPTOS)} crypto valide.")

st.markdown("---")
st.markdown("**ℹ️ TREND FOLLOWING PURO (v4):**")
st.markdown("• Entra quando: prezzo > EMA Fast > EMA Slow (Trend UP confermato)")
st.markdown("• Esce quando: prezzo scende sotto EMA Fast (Trend gira)")
st.markdown("• Niente TP/SL rigidi — segue il movimento naturale")
st.markdown("• Testa 10 combinazioni di EMA per trovare la migliore")
