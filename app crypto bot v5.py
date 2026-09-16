import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime, timezone, timedelta

st.set_page_config(page_title="Crypto Bot Simulator", layout="wide")
st.title("🤖 Crypto Trading Bot - Mean Reversion V5")
st.markdown("Strategia MEAN REVERSION: sfrutta rimbalzi quando prezzo scende troppo")

BASE = "https://api.coinbase.com/api/v3/brokerage/market/products/{product_id}/candles"
TOP_CRYPTOS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD",
    "AVAX-USD", "DOGE-USD", "MATIC-USD", "LTC-USD", "UNI-USD",
    "LINK-USD", "ATOM-USD", "POLKADOT-USD", "SHIB-USD", "TRX-USD",
    "NEAR-USD", "FIL-USD", "PEPE-USD", "BLUR-USD", "BONK-USD"
]

FEE = 0.005

st.sidebar.header("⚙️ Parametri")
initial_capital = st.sidebar.number_input("Capitale iniziale (€)", value=10.0, min_value=1.0, step=1.0)
days = st.sidebar.number_input("Giorni recenti", value=30, min_value=7, max_value=90, step=5)

st.sidebar.header("💰 Soglie accantonamento")
threshold1 = st.sidebar.number_input("Soglia 1 (€)", value=1.0, min_value=0.1, step=0.1)
acc1 = st.sidebar.number_input("Accantona % 1", value=80, min_value=0, max_value=100) / 100
threshold2 = st.sidebar.number_input("Soglia 2 (€)", value=5.0, min_value=1.0, step=1.0)
acc2 = st.sidebar.number_input("Accantona % 2", value=90, min_value=0, max_value=100) / 100
threshold3 = st.sidebar.number_input("Soglia 3 (€)", value=10.0, min_value=5.0, step=5.0)
acc3 = st.sidebar.number_input("Accantona % 3", value=95, min_value=0, max_value=100) / 100

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

def backtest_mean_reversion(data_dict, initial_capital, th1, a1, th2, a2, th3, a3):
    variants = [
        {"name": "MR_SMA50_3%", "sma": 50, "dev": 0.03},
        {"name": "MR_SMA30_2%", "sma": 30, "dev": 0.02},
        {"name": "MR_SMA100_5%", "sma": 100, "dev": 0.05},
        {"name": "MR_SMA40_3.5%", "sma": 40, "dev": 0.035},
        {"name": "MR_SMA60_4%", "sma": 60, "dev": 0.04},
        {"name": "MR_SMA50_2.5%", "sma": 50, "dev": 0.025},
        {"name": "MR_SMA80_4.5%", "sma": 80, "dev": 0.045},
        {"name": "MR_SMA35_3%", "sma": 35, "dev": 0.03},
        {"name": "MR_SMA70_3.5%", "sma": 70, "dev": 0.035},
        {"name": "MR_SMA45_3%", "sma": 45, "dev": 0.03},
    ]
    
    results = []
    
    for variant in variants:
        ind_dict = {}
        for crypto, df in data_dict.items():
            if df is not None and len(df) > variant["sma"] + 20:
                d = df.copy()
                d["sma"] = d["close"].rolling(variant["sma"]).mean()
                ind_dict[crypto] = d
        
        if not ind_dict:
            continue
        
        num_candles = len(list(ind_dict.values())[0])
        trading_capital = initial_capital
        accantonato = 0.0
        position = None
        trades = []
        
        start_idx = variant["sma"] + 20
        
        for i in range(start_idx, num_candles - 1):
            if position is None:
                best_crypto = None
                best_discount = 0
                
                for crypto, ind_df in ind_dict.items():
                    if i < len(ind_df):
                        row = ind_df.iloc[i]
                        if pd.notna(row["sma"]):
                            price = float(row["close"])
                            sma = float(row["sma"])
                            lower_bound = sma * (1 - variant["dev"])
                            
                            if price < lower_bound:
                                discount = (sma - price) / sma
                                if discount > best_discount:
                                    best_discount = discount
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
                        "sma": float(ind_df.iloc[i]["sma"]),
                    }
            else:
                crypto = position["crypto"]
                ind_df = ind_dict[crypto]
                
                if i + 1 < len(ind_df):
                    nxt = ind_df.iloc[i + 1]
                    price = float(nxt.close)
                    sma = float(nxt["sma"]) if pd.notna(nxt["sma"]) else position["sma"]
                    
                    upper_bound = sma * (1 + variant["dev"] * 0.5)
                    exit_condition = price > upper_bound or price > position["sma"] * 1.02 or price < position["entry_price"] * 0.98
                    
                    if exit_condition:
                        exit_price = float(nxt.close)
                        gross = exit_price / position["entry_price"] - 1
                        net_factor = (1 + gross) * (1 - FEE) * (1 - FEE)
                        new_capital = position["entry_capital"] * net_factor
                        
                        trades.append({"net_pct": (new_capital/position["entry_capital"]-1)*100})
                        
                        trading_capital = new_capital
                        total_capital = trading_capital + accantonato
                        profitto = total_capital - initial_capital
                        
                        if profitto >= th3:
                            da_acc = (trading_capital - position["entry_capital"]) * a3
                            if da_acc > 0:
                                accantonato += da_acc
                                trading_capital -= da_acc
                        elif profitto >= th2:
                            da_acc = (trading_capital - position["entry_capital"]) * a2
                            if da_acc > 0:
                                accantonato += da_acc
                                trading_capital -= da_acc
                        elif profitto >= th1:
                            da_acc = (trading_capital - position["entry_capital"]) * a1
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
            "sma": variant["sma"],
            "dev": f"{variant['dev']*100:.1f}%",
            "trades": num_trades,
            "wins": wins,
            "win_rate": win_rate,
            "capital": total_capital,
            "profitto": profitto,
            "profitto_pct": profitto_pct
        })
    
    return results

st.markdown(f"**Capitale:** €{initial_capital} | **Giorni:** {days} | **Crypto:** {len(TOP_CRYPTOS)}")

if st.button("▶️ Esegui Mean Reversion Optimization", key="simulate"):
    st.info(f"⏳ Download dati...")
    
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
    
    valid = [c for c, df in data_dict.items() if df is not None and len(df) > 150]
    
    if len(valid) >= 12:
        st.success(f"✓ {len(valid)} crypto valide")
        
        st.info("🔍 Testing 10 varianti Mean Reversion...")
        with st.spinner("Analisi..."):
            results = backtest_mean_reversion(data_dict, initial_capital, threshold1, acc1, threshold2, acc2, threshold3, acc3)
        
        if results:
            df_res = pd.DataFrame(results)
            best_idx = df_res["profitto_pct"].idxmax()
            best = df_res.iloc[best_idx]
            
            st.success(f"✅ Migliore: **{best['variant']}**")
            
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("💰 Finale", f"€{best['capital']:.2f}")
            col2.metric("💹 Profitto", f"€{best['profitto']:.2f}")
            col3.metric("📈 %", f"{best['profitto_pct']:.2f}%")
            col4.metric("Trade", int(best['trades']))
            col5.metric("Win %", f"{best['win_rate']:.1f}%")
            
            st.subheader("📊 Tutte le Varianti")
            display = df_res[["variant", "sma", "dev", "trades", "win_rate", "profitto", "profitto_pct"]].copy()
            display.columns = ["Strategia", "SMA", "Deviation", "Trade", "Win %", "Profitto €", "Profitto %"]
            st.dataframe(display, use_container_width=True)
            
            csv = df_res.to_csv(index=False)
            st.download_button(label="📥 Scarica CSV", data=csv, file_name=f"mean_reversion_{days}d.csv", mime="text/csv")
        else:
            st.error("❌ Errore")
    else:
        st.error(f"❌ Dati insufficienti")

st.markdown("---")
st.markdown("**Mean Reversion: sfrutta rimbalzi**")
st.markdown("• Entra quando prezzo scende X% sotto la media")
st.markdown("• Esce quando prezzo ritorna alla media (rimbalzo)")
st.markdown("• Funziona su 30 giorni (movimento veloce)")
