import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime, timezone, timedelta
import matplotlib.pyplot as plt

# Configurazione Streamlit
st.set_page_config(page_title="Crypto Bot Simulator", layout="wide")
st.title("🤖 Crypto Trading Bot Simulator - Live Recente")
st.markdown("Simula il bot autonomo sui dati **REALI degli ultimi giorni** - Mercato attuale, non passato")

# Costanti
BASE = "https://api.coinbase.com/api/v3/brokerage/market/products/{product_id}/candles"

# TOP 20 CRYPTO COINBASE (VERIFICATE E STABILI)
TOP_CRYPTOS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD",
    "AVAX-USD", "DOGE-USD", "MATIC-USD", "LTC-USD", "UNI-USD",
    "LINK-USD", "ATOM-USD", "POLKADOT-USD", "SHIB-USD", "TRX-USD",
    "NEAR-USD", "FIL-USD", "PEPE-USD", "BLUR-USD", "BONK-USD"
]

FEE = 0.005
TP = 0.03  # +3% quando vende in profitto
SL = 0.015  # -1.5% per stop loss
MIN_SCORE = 70  # Score minimo per entrare
EXIT_SCORE = 50  # Score per uscire da posizione

# Sidebar per input
st.sidebar.header("⚙️ Parametri")
initial_capital = st.sidebar.number_input("Capitale iniziale (€)", value=10.0, min_value=1.0, step=1.0)
days = st.sidebar.number_input("Giorni recenti da ORA", value=30, min_value=7, max_value=90, step=5)
st.sidebar.caption(f"📅 Simula sui dati reali degli ultimi {days} giorni")

st.sidebar.header("💰 Soglie di accantonamento")
st.sidebar.markdown("Quando profitto >= soglia, accantona % e continua con il resto")
threshold1 = st.sidebar.number_input("Soglia 1 (€ profitto)", value=1.0, min_value=0.1, step=0.1)
accantonamento1 = st.sidebar.number_input("Accantona % soglia 1", value=80, min_value=0, max_value=100) / 100

threshold2 = st.sidebar.number_input("Soglia 2 (€ profitto)", value=5.0, min_value=1.0, step=1.0)
accantonamento2 = st.sidebar.number_input("Accantona % soglia 2", value=90, min_value=0, max_value=100) / 100

threshold3 = st.sidebar.number_input("Soglia 3 (€ profitto)", value=10.0, min_value=5.0, step=5.0)
accantonamento3 = st.sidebar.number_input("Accantona % soglia 3", value=95, min_value=0, max_value=100) / 100

st.sidebar.markdown("---")
st.sidebar.info(f"🤖 Bot 100% autonomo su {len(TOP_CRYPTOS)} crypto\n📊 Dati: ultimi {days} giorni reali\n⏱️ Mercato attuale, non passato")

def fetch_candles(product, days):
    """Scarica candele 1h da Coinbase per gli ultimi N giorni"""
    end = int(time.time())
    start = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    
    all_candles = []
    step = 350 * 3600
    cur = start
    request_count = 0
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    while cur < end:
        nxt = min(cur + step, end)
        request_count += 1
        
        params = {
            "start": str(cur), "end": str(nxt),
            "granularity": "ONE_HOUR", "limit": 350
        }
        
        try:
            status_text.text(f"Download... Richiesta {request_count}")
            r = requests.get(BASE.format(product_id=product), params=params, timeout=20)
            
            if r.status_code != 200:
                st.error(f"Errore Coinbase: HTTP {r.status_code}")
                return None
            
            data = r.json().get("candles", [])
            if data:
                all_candles.extend(data)
            
            cur = nxt
            progress_bar.progress(min((cur - start) / (end - start), 1.0))
            time.sleep(0.15)
            
        except Exception as e:
            st.error(f"Errore di connessione: {e}")
            return None
    
    progress_bar.empty()
    status_text.empty()
    
    if not all_candles:
        return None
    
    # Costruisci DataFrame
    df = pd.DataFrame(all_candles)
    
    # Converti campi
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    
    df["start"] = pd.to_numeric(df["start"], errors="coerce").astype(int)
    df["time"] = pd.to_datetime(df["start"], unit="s", utc=True)
    
    # Ordina e deduplicato
    df = df.sort_values("time")
    df = df.drop_duplicates("start")
    df = df.set_index("time")[["open", "high", "low", "close", "volume"]]
    
    return df

def calculate_indicators(df):
    """Calcola EMA, RSI, MACD"""
    d = df.copy()
    d["ema20"] = d.close.ewm(span=20, adjust=False).mean()
    d["ema50"] = d.close.ewm(span=50, adjust=False).mean()
    d["ema200"] = d.close.ewm(span=200, adjust=False).mean()

    delta = d.close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    d["rsi"] = 100 - (100 / (1 + rs))

    ema12 = d.close.ewm(span=12, adjust=False).mean()
    ema26 = d.close.ewm(span=26, adjust=False).mean()
    d["macd"] = ema12 - ema26
    d["macd_signal"] = d.macd.ewm(span=9, adjust=False).mean()

    d["vol_ma20"] = d.volume.rolling(20).mean()
    tr = pd.concat([
        d.high-d.low,
        (d.high-d.close.shift()).abs(),
        (d.low-d.close.shift()).abs()
    ], axis=1).max(axis=1)
    d["atr"] = tr.rolling(14).mean()
    return d

def score(row):
    """Calcola score di ingresso"""
    s = 0
    if row.close > row.ema20: s += 15
    if row.ema20 > row.ema50: s += 15
    if row.ema50 > row.ema200: s += 15
    if 50 <= row.rsi <= 68: s += 15
    if row.macd > row.macd_signal: s += 15
    if row.volume > row.vol_ma20: s += 10
    if row.atr / row.close < 0.04: s += 5
    return s

def test_parameter_variants(data_dict, initial_capital, threshold1, acc1, threshold2, acc2, threshold3, acc3):
    """
    Testa 10 varianti diverse di parametri (TP, SL, MIN_SCORE, EXIT_SCORE).
    Restituisce i risultati di tutte le varianti e identifica la migliore.
    """
    
    # Definisci 10 varianti di parametri
    variants = [
        {"name": "Conservative", "tp": 0.02, "sl": 0.01, "min_score": 75, "exit_score": 55},
        {"name": "Aggressive", "tp": 0.05, "sl": 0.02, "min_score": 65, "exit_score": 45},
        {"name": "Balanced", "tp": 0.03, "sl": 0.015, "min_score": 70, "exit_score": 50},
        {"name": "High Profit", "tp": 0.04, "sl": 0.015, "min_score": 72, "exit_score": 52},
        {"name": "Low Risk", "tp": 0.025, "sl": 0.008, "min_score": 78, "exit_score": 58},
        {"name": "Quick Exit", "tp": 0.025, "sl": 0.02, "min_score": 68, "exit_score": 48},
        {"name": "Trend Follow", "tp": 0.035, "sl": 0.012, "min_score": 70, "exit_score": 52},
        {"name": "Volatile", "tp": 0.045, "sl": 0.025, "min_score": 65, "exit_score": 42},
        {"name": "Stable", "tp": 0.015, "sl": 0.01, "min_score": 76, "exit_score": 56},
        {"name": "Optimal", "tp": 0.032, "sl": 0.016, "min_score": 71, "exit_score": 51},
    ]
    
    results = []
    
    for idx, variant in enumerate(variants):
        # Calcola indicatori per tutte le crypto
        indicators_dict = {}
        for crypto, df in data_dict.items():
            if df is not None and len(df) > 220:
                indicators_dict[crypto] = calculate_indicators(df)
        
        if not indicators_dict:
            continue
        
        # Esegui backtest con questi parametri
        num_candles = len(list(indicators_dict.values())[0])
        trading_capital = initial_capital
        accantonato = 0.0
        position = None
        trades = []
        
        for i in range(220, num_candles - 1):
            if position is None:
                best_crypto = None
                best_score = variant["min_score"] - 1
                
                for crypto, ind_df in indicators_dict.items():
                    if i < len(ind_df):
                        row = ind_df.iloc[i]
                        sc = score(row)
                        
                        if sc > best_score:
                            best_score = sc
                            best_crypto = crypto
                
                if best_crypto is not None and best_score >= variant["min_score"]:
                    ind_df = indicators_dict[best_crypto]
                    nxt = ind_df.iloc[i + 1]
                    entry_price = float(nxt.open)
                    
                    position = {
                        "crypto": best_crypto,
                        "entry_price": entry_price,
                        "entry_time": ind_df.index[i + 1],
                        "entry_capital": trading_capital,
                        "entry_score": best_score,
                    }
            else:
                crypto = position["crypto"]
                ind_df = indicators_dict[crypto]
                
                if i + 1 < len(ind_df):
                    nxt = ind_df.iloc[i + 1]
                    row = ind_df.iloc[i]
                    current_score = score(row)
                    
                    exit_price = None
                    reason = None
                    
                    if nxt.low <= position["entry_price"] * (1 - variant["sl"]):
                        exit_price = position["entry_price"] * (1 - variant["sl"])
                        reason = "SL"
                    elif nxt.high >= position["entry_price"] * (1 + variant["tp"]):
                        exit_price = position["entry_price"] * (1 + variant["tp"])
                        reason = "TP"
                    elif current_score < variant["exit_score"]:
                        exit_price = float(nxt.close)
                        reason = "TREND"
                    elif nxt.close < nxt.ema50:
                        exit_price = float(nxt.close)
                        reason = "EMA"
                    
                    if exit_price is not None:
                        gross = exit_price / position["entry_price"] - 1
                        net_factor = (1 + gross) * (1 - FEE) * (1 - FEE)
                        new_capital = position["entry_capital"] * net_factor
                        
                        trades.append({
                            "entry": position["entry_price"],
                            "exit": exit_price,
                            "net_pct": (new_capital/position["entry_capital"]-1)*100
                        })
                        
                        trading_capital = new_capital
                        
                        # Accantonamento
                        total_capital = trading_capital + accantonato
                        profitto = total_capital - initial_capital
                        
                        if profitto >= threshold3:
                            da_accantonare = (trading_capital - position["entry_capital"]) * acc3
                            if da_accantonare > 0:
                                accantonato += da_accantonare
                                trading_capital -= da_accantonare
                        elif profitto >= threshold2:
                            da_accantonare = (trading_capital - position["entry_capital"]) * acc2
                            if da_accantonare > 0:
                                accantonato += da_accantonare
                                trading_capital -= da_accantonare
                        elif profitto >= threshold1:
                            da_accantonare = (trading_capital - position["entry_capital"]) * acc1
                            if da_accantonare > 0:
                                accantonato += da_accantonare
                                trading_capital -= da_accantonare
                        
                        position = None
        
        # Calcola statistiche per questa variante
        total_capital = trading_capital + accantonato
        profitto_totale = total_capital - initial_capital
        profitto_pct = (profitto_totale / initial_capital) * 100
        num_trades = len(trades)
        wins = len([t for t in trades if t["net_pct"] > 0]) if trades else 0
        win_rate = (wins / num_trades * 100) if num_trades > 0 else 0
        
        results.append({
            "variant": variant["name"],
            "tp": variant["tp"],
            "sl": variant["sl"],
            "min_score": variant["min_score"],
            "exit_score": variant["exit_score"],
            "trades": num_trades,
            "wins": wins,
            "win_rate": win_rate,
            "capital": total_capital,
            "profitto": profitto_totale,
            "profitto_pct": profitto_pct
        })
    
    return results
    """
    Backtest autonomo multi-crypto.
    Il bot sceglie quale crypto comprare/vendere in base al score migliore.
    """
    # Calcola indicatori per tutte le crypto
    indicators_dict = {}
    for crypto, df in data_dict.items():
        if df is not None and len(df) > 220:
            indicators_dict[crypto] = calculate_indicators(df)
    
    if not indicators_dict:
        return None, None, None, None
    
    # Trova il numero di candele (stesso per tutte)
    num_candles = len(list(indicators_dict.values())[0])
    
    trading_capital = initial_capital
    accantonato = 0.0
    position = None  # {"crypto": "BTC-USD", "entry_price": X, "entry_time": T, "entry_capital": X}
    trades = []
    capital_history = []
    
    start_idx = 220
    
    for i in range(start_idx, num_candles - 1):
        # Se non hai posizione, cerca la crypto migliore
        if position is None:
            best_crypto = None
            best_score = MIN_SCORE - 1
            
            for crypto, ind_df in indicators_dict.items():
                if i < len(ind_df):
                    row = ind_df.iloc[i]
                    sc = score(row)
                    
                    if sc > best_score:
                        best_score = sc
                        best_crypto = crypto
            
            # Se trovata una crypto buona, entra
            if best_crypto is not None and best_score >= MIN_SCORE:
                ind_df = indicators_dict[best_crypto]
                nxt = ind_df.iloc[i + 1]
                entry_price = float(nxt.open)
                
                position = {
                    "crypto": best_crypto,
                    "entry_price": entry_price,
                    "entry_time": ind_df.index[i + 1],
                    "entry_capital": trading_capital,
                    "entry_score": best_score,
                    "entry_idx": i + 1
                }
        
        # Se hai posizione, monitora quella crypto
        else:
            crypto = position["crypto"]
            ind_df = indicators_dict[crypto]
            
            if i + 1 < len(ind_df):
                nxt = ind_df.iloc[i + 1]
                row = ind_df.iloc[i]
                current_score = score(row)
                
                exit_price = None
                reason = None
                
                # Criteri di uscita
                # 1. Hit TP o SL
                if nxt.low <= position["entry_price"] * (1 - SL):
                    exit_price = position["entry_price"] * (1 - SL)
                    reason = "STOP_LOSS"
                elif nxt.high >= position["entry_price"] * (1 + TP):
                    exit_price = position["entry_price"] * (1 + TP)
                    reason = "TAKE_PROFIT"
                # 2. Score scende troppo (trend gira)
                elif current_score < EXIT_SCORE:
                    exit_price = float(nxt.close)
                    reason = "TREND_EXIT"
                # 3. Chiude sotto EMA50 (trend negativo)
                elif nxt.close < nxt.ema50:
                    exit_price = float(nxt.close)
                    reason = "EMA50_EXIT"
                
                if exit_price is not None:
                    # Calcola profitto
                    gross = exit_price / position["entry_price"] - 1
                    net_factor = (1 + gross) * (1 - FEE) * (1 - FEE)
                    new_capital = position["entry_capital"] * net_factor
                    
                    trades.append({
                        "entry_time": position["entry_time"],
                        "exit_time": ind_df.index[i + 1],
                        "crypto": crypto,
                        "entry": position["entry_price"],
                        "exit": exit_price,
                        "score": position["entry_score"],
                        "reason": reason,
                        "gross_pct": gross*100,
                        "net_pct": (new_capital/position["entry_capital"]-1)*100,
                        "capital_after": new_capital
                    })
                    
                    trading_capital = new_capital
                    
                    # Verifica accantonamento
                    total_capital = trading_capital + accantonato
                    profitto = total_capital - initial_capital
                    
                    if profitto >= threshold3:
                        da_accantonare = (trading_capital - position["entry_capital"]) * acc3
                        if da_accantonare > 0:
                            accantonato += da_accantonare
                            trading_capital -= da_accantonare
                    elif profitto >= threshold2:
                        da_accantonare = (trading_capital - position["entry_capital"]) * acc2
                        if da_accantonare > 0:
                            accantonato += da_accantonare
                            trading_capital -= da_accantonare
                    elif profitto >= threshold1:
                        da_accantonare = (trading_capital - position["entry_capital"]) * acc1
                        if da_accantonare > 0:
                            accantonato += da_accantonare
                            trading_capital -= da_accantonare
                    
                    position = None
        
        # Registra capitale ogni 24 candele (ogni giorno)
        if i % 24 == 0:
            first_crypto = list(indicators_dict.keys())[0]
            first_df = indicators_dict[first_crypto]
            if i < len(first_df):
                capital_history.append({
                    "time": first_df.index[i],
                    "trading": trading_capital,
                    "accantonato": accantonato
                })
    
    return trading_capital, accantonato, trades, capital_history

# Main
st.markdown(f"**Capitale iniziale:** €{initial_capital} | **Dati:** ultimi {days} giorni (reali, da ORA) | **Asset:** TOP {len(TOP_CRYPTOS)} Crypto")

if st.button("▶️ Esegui Simulazione Autonoma + Optimization", key="simulate"):
    st.info(f"⏳ Scaricamento dati da Coinbase per {len(TOP_CRYPTOS)} crypto...")
    
    # Scarica tutte le crypto
    data_dict = {}
    progress = st.progress(0)
    
    for idx, crypto in enumerate(TOP_CRYPTOS):
        try:
            progress.progress((idx + 1) / len(TOP_CRYPTOS))
            df = fetch_candles(crypto, days)
            if df is not None:
                data_dict[crypto] = df
        except:
            continue
    
    progress.empty()
    
    # Verifica crypto valide
    valid_cryptos = [c for c, df in data_dict.items() if df is not None and len(df) > 250]
    
    if len(valid_cryptos) >= 12:
        st.success(f"✓ Scaricate {len(valid_cryptos)} crypto valide")
        
        # Esegui Optimization Loop
        st.info("🔍 Optimization Loop: testing 10 varianti di parametri...")
        with st.spinner("Analisi in corso (1-2 minuti)..."):
            variants_results = test_parameter_variants(
                data_dict, initial_capital,
                threshold1, accantonamento1,
                threshold2, accantonamento2,
                threshold3, accantonamento3
            )
        
        if variants_results:
            # Converti in DataFrame
            variants_df = pd.DataFrame(variants_results)
            
            # Trova la migliore (per profitto %)
            best_idx = variants_df["profitto_pct"].idxmax()
            best_variant = variants_df.iloc[best_idx]
            
            st.success(f"✅ Migliore variante trovata: **{best_variant['variant']}**")
            
            # Mostra risultato della migliore
            st.subheader("🏆 Risultato Migliore")
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("💰 Capitale Finale", f"€{best_variant['capital']:.2f}")
            col2.metric("💹 Profitto", f"€{best_variant['profitto']:.2f}")
            col3.metric("📈 +%", f"{best_variant['profitto_pct']:.2f}%")
            col4.metric("📋 N. Trade", int(best_variant['trades']))
            col5.metric("✅ Win Rate", f"{best_variant['win_rate']:.1f}%")
            
            # Mostra parametri migliori
            st.markdown(f"**Parametri Ottimali trovati:**")
            st.markdown(f"• TP: +{best_variant['tp']*100:.1f}% | SL: -{best_variant['sl']*100:.1f}% | Min Score: {int(best_variant['min_score'])} | Exit Score: {int(best_variant['exit_score'])}")
            
            # Tabella comparativa di tutte le 10 varianti
            st.subheader("📊 Confronto Tutte le Varianti")
            display_variants = variants_df[["variant", "tp", "sl", "min_score", "exit_score", "trades", "win_rate", "profitto", "profitto_pct"]].copy()
            display_variants["tp"] = (display_variants["tp"] * 100).round(1).astype(str) + "%"
            display_variants["sl"] = (display_variants["sl"] * 100).round(1).astype(str) + "%"
            display_variants.rename(columns={
                "variant": "Variante",
                "tp": "TP",
                "sl": "SL",
                "min_score": "Score",
                "exit_score": "Exit",
                "trades": "Trade",
                "win_rate": "Win %",
                "profitto": "Profitto €",
                "profitto_pct": "Profitto %"
            }, inplace=True)
            
            # Evidenzia la migliore riga
            def highlight_best(row):
                if row["Variante"] == best_variant["variant"]:
                    return ["background-color: #2d7a2d"] * len(row)
                return [""] * len(row)
            
            styled_df = display_variants.style.apply(highlight_best, axis=1)
            st.dataframe(styled_df, use_container_width=True)
            
            # CSV download
            csv = variants_df.to_csv(index=False)
            st.download_button(
                label="📥 Scarica Risultati Optimization CSV",
                data=csv,
                file_name=f"optimization_results_{days}d.csv",
                mime="text/csv"
            )
        else:
            st.error("❌ Errore nel testing delle varianti")
    else:
        st.error(f"❌ Dati insufficienti: {len(valid_cryptos)}/{len(TOP_CRYPTOS)} crypto valide.")

st.markdown("---")
st.markdown("**ℹ️ OPZIONE C + OPTIMIZATION LOOP v3:**")
st.markdown("• Usa dati **reali degli ultimi giorni** (mercato ADESSO)")
st.markdown("• **Testa 10 varianti di parametri** (TP, SL, Score, Exit)")
st.markdown("• Identifica la **variante ottimale** per il mercato attuale")
st.markdown("• Mostra confronto di tutte le 10 versioni")
st.markdown("• Bot impara e si adatta autonomamente")
st.markdown("• ⏱️ Tempo: ~10-15 minuti (testa tutte le varianti)")
