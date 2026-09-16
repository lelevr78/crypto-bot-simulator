import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime, timezone, timedelta

st.set_page_config(page_title="Crypto Bot Simulator", layout="wide")
st.title("🤖 Crypto Trading Bot - Mean Reversion V8")
st.markdown("Strategia V8: mean reversion con conferma di rimbalzo, RSI e stop/target basati sulla volatilità")

BASE = "https://api.exchange.coinbase.com/products/{product_id}/candles"
TOP_CRYPTOS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD",
    "AVAX-USD", "DOGE-USD", "POL-USD", "LTC-USD", "UNI-USD",
    "LINK-USD", "ATOM-USD", "DOT-USD", "SHIB-USD", "TRX-USD",
    "NEAR-USD", "FIL-USD", "PEPE-USD", "BLUR-USD", "BONK-USD"
]

FEE = 0.005  # 0,50% per lato, come simulazione conservativa

st.sidebar.header("⚙️ Parametri")
initial_capital = st.sidebar.number_input("Capitale iniziale (€)", value=10.0, min_value=1.0, step=1.0)
days = st.sidebar.number_input("Giorni recenti", value=120, min_value=30, max_value=120, step=10)

st.sidebar.header("💰 Soglie accantonamento")
threshold1 = st.sidebar.number_input("Soglia 1 (€)", value=1.0, min_value=0.1, step=0.1)
acc1 = st.sidebar.number_input("Accantona % 1", value=80, min_value=0, max_value=100) / 100
threshold2 = st.sidebar.number_input("Soglia 2 (€)", value=5.0, min_value=1.0, step=1.0)
acc2 = st.sidebar.number_input("Accantona % 2", value=90, min_value=0, max_value=100) / 100
threshold3 = st.sidebar.number_input("Soglia 3 (€)", value=10.0, min_value=5.0, step=5.0)
acc3 = st.sidebar.number_input("Accantona % 3", value=95, min_value=0, max_value=100) / 100

def fetch_candles(product, days):
    """Scarica e valida candele Coinbase Exchange 1h.

    Ritorna (DataFrame, None) se valido oppure (None, motivo) se il
    prodotto non è disponibile o il dataset non supera i controlli.
    Non nasconde più gli errori.
    """
    end = (int(time.time()) // 3600) * 3600
    start = end - int(days) * 24 * 3600

    # Coinbase Exchange: massimo 300 candele per richiesta.
    step = 300 * 3600
    rows = []
    cur = start
    request_no = 0

    while cur < end:
        nxt = min(cur + step, end)
        request_no += 1

        params = {
            "start": str(cur),
            "end": str(nxt),
            "granularity": 3600,
        }

        try:
            r = requests.get(
                BASE.format(product_id=product),
                params=params,
                timeout=30,
                headers={"User-Agent": "CryptoBotSimulator/8.0"},
            )
        except requests.RequestException as e:
            return None, f"errore rete: {e}"

        if r.status_code != 200:
            try:
                detail = r.json()
            except Exception:
                detail = r.text[:250].replace("\n", " ")
            return None, f"HTTP {r.status_code}: {detail}"

        try:
            data = r.json()
        except ValueError:
            return None, "risposta JSON non valida"

        if not isinstance(data, list):
            return None, "formato risposta inatteso"

        if not data:
            return None, (
                "nessuna candela restituita nella finestra "
                f"{datetime.fromtimestamp(cur, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')} → "
                f"{datetime.fromtimestamp(nxt, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC"
            )

        valid_in_window = 0

        for item in data:
            if not isinstance(item, list) or len(item) < 6:
                return None, "candela con formato non valido"

            try:
                ts = int(item[0])
            except (TypeError, ValueError):
                return None, "timestamp non valido"

            # L'Exchange API può includere il bordo end: il test usa [start, end).
            if cur <= ts < nxt:
                rows.append({
                    "start": ts,
                    "low": item[1],
                    "high": item[2],
                    "open": item[3],
                    "close": item[4],
                    "volume": item[5],
                })
                valid_in_window += 1

        if valid_in_window == 0:
            return None, (
                "la risposta non contiene candele dentro la finestra richiesta; "
                "possibile problema di copertura/API"
            )

        cur = nxt
        time.sleep(0.08)

    if not rows:
        return None, "nessun dato ricevuto"

    df = pd.DataFrame(rows)

    for c in ["start", "open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    if df[["start", "open", "high", "low", "close", "volume"]].isna().any().any():
        return None, "valori OHLCV mancanti o non numerici"

    df["start"] = df["start"].astype("int64")
    df = df.sort_values("start")

    duplicates = int(df["start"].duplicated().sum())
    if duplicates:
        return None, f"{duplicates} timestamp duplicati"

    expected = int(days) * 24

    if len(df) != expected:
        return None, f"{len(df)} candele, attese {expected}"

    expected_last = end - 3600

    if int(df["start"].iloc[0]) != start:
        first = datetime.fromtimestamp(int(df["start"].iloc[0]), tz=timezone.utc).isoformat()
        wanted = datetime.fromtimestamp(start, tz=timezone.utc).isoformat()
        return None, f"prima candela {first}, attesa {wanted}"

    if int(df["start"].iloc[-1]) != expected_last:
        last = datetime.fromtimestamp(int(df["start"].iloc[-1]), tz=timezone.utc).isoformat()
        wanted = datetime.fromtimestamp(expected_last, tz=timezone.utc).isoformat()
        return None, f"ultima candela {last}, attesa {wanted}"

    diffs = df["start"].diff().dropna().to_numpy()
    if len(diffs) and np.any(diffs != 3600):
        bad = int(np.where(diffs != 3600)[0][0]) + 1
        p = int(df["start"].iloc[bad - 1])
        n = int(df["start"].iloc[bad])
        return None, (
            "gap temporale tra "
            f"{datetime.fromtimestamp(p, tz=timezone.utc).isoformat()} e "
            f"{datetime.fromtimestamp(n, tz=timezone.utc).isoformat()}"
        )

    df["time"] = pd.to_datetime(df["start"], unit="s", utc=True)
    df = df.set_index("time")[["open", "high", "low", "close", "volume"]]

    return df, None


def backtest_mean_reversion(data_dict, initial_capital, th1, a1, th2, a2, th3, a3):
    """
    V8: mean reversion a due fasi.

    1) Setup: deviazione dalla SMA + RSI basso.
    2) Conferma: candela positiva, close > close precedente e RSI in
       miglioramento. L'ingresso avviene sulla candela successiva.

    Le uscite sono:
    - stop ATR
    - target
    - ritorno alla SMA
    - trailing dopo un profitto minimo
    - time stop

    Il capitale non viene accantonato durante il backtest: il rendimento
    misura esclusivamente la strategia di trading.
    """

    variants = [
        {"name": "V8_A", "sma": 50, "dev": 0.025, "rsi": 34, "atr_stop": 1.7, "tp": 0.025, "max_hours": 36},
        {"name": "V8_B", "sma": 50, "dev": 0.030, "rsi": 32, "atr_stop": 1.8, "tp": 0.030, "max_hours": 48},
        {"name": "V8_C", "sma": 60, "dev": 0.030, "rsi": 34, "atr_stop": 1.8, "tp": 0.028, "max_hours": 48},
        {"name": "V8_D", "sma": 70, "dev": 0.030, "rsi": 32, "atr_stop": 1.9, "tp": 0.030, "max_hours": 48},
        {"name": "V8_E", "sma": 80, "dev": 0.035, "rsi": 32, "atr_stop": 1.9, "tp": 0.032, "max_hours": 60},
        {"name": "V8_F", "sma": 80, "dev": 0.040, "rsi": 30, "atr_stop": 2.0, "tp": 0.035, "max_hours": 72},
        {"name": "V8_G", "sma": 100, "dev": 0.040, "rsi": 32, "atr_stop": 2.0, "tp": 0.035, "max_hours": 72},
        {"name": "V8_H", "sma": 60, "dev": 0.035, "rsi": 30, "atr_stop": 1.9, "tp": 0.032, "max_hours": 60},
        {"name": "V8_I", "sma": 70, "dev": 0.035, "rsi": 31, "atr_stop": 1.9, "tp": 0.030, "max_hours": 60},
        {"name": "V8_J", "sma": 90, "dev": 0.035, "rsi": 32, "atr_stop": 2.0, "tp": 0.035, "max_hours": 72},
    ]

    results = []
    all_trades = []

    for variant in variants:
        ind = {}

        for crypto, df in data_dict.items():
            if df is None or len(df) <= variant["sma"] + 30:
                continue

            d = df.copy()
            d["sma"] = d["close"].rolling(variant["sma"]).mean()

            delta = d["close"].diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs = gain / loss.replace(0, np.nan)
            d["rsi"] = 100 - (100 / (1 + rs))

            prev_close = d["close"].shift(1)
            tr = pd.concat([
                d["high"] - d["low"],
                (d["high"] - prev_close).abs(),
                (d["low"] - prev_close).abs()
            ], axis=1).max(axis=1)

            d["atr"] = tr.rolling(14).mean()
            d["vol_ma"] = d["volume"].rolling(20).mean()
            ind[crypto] = d

        if not ind:
            continue

        common_index = None
        for d in ind.values():
            common_index = d.index if common_index is None else common_index.intersection(d.index)

        if common_index is None or len(common_index) < variant["sma"] + 40:
            continue

        for crypto in list(ind.keys()):
            ind[crypto] = ind[crypto].loc[common_index]

        capital = float(initial_capital)
        position = None
        trades = []
        peak_capital = capital
        max_drawdown = 0.0

        for i in range(max(variant["sma"], 30) + 5, len(common_index) - 2):
            # ---------- ENTRY ----------
            if position is None:
                candidates = []

                for crypto, d in ind.items():
                    row = d.iloc[i]
                    prev = d.iloc[i - 1]

                    needed = ["sma", "rsi", "atr", "vol_ma"]
                    if not all(pd.notna(row[c]) for c in needed):
                        continue
                    if not all(pd.notna(prev[c]) for c in ["rsi", "close"]):
                        continue

                    close = float(row["close"])
                    open_price = float(row["open"])
                    prev_close_val = float(prev["close"])
                    sma = float(row["sma"])
                    rsi = float(row["rsi"])
                    prev_rsi = float(prev["rsi"])
                    atr = float(row["atr"])
                    vol_ma = float(row["vol_ma"])
                    volume = float(row["volume"])

                    if sma <= 0 or atr <= 0 or vol_ma <= 0:
                        continue

                    discount = (sma - close) / sma

                    # Fase 1: setup.
                    setup = discount >= variant["dev"] and rsi <= variant["rsi"]

                    # Fase 2: conferma di rimbalzo.
                    bullish = close > open_price and close > prev_close_val
                    rsi_improving = rsi > prev_rsi
                    volume_ok = volume >= vol_ma * 0.5

                    if setup and bullish and rsi_improving and volume_ok:
                        # Score: preferiamo un segnale forte, ma non
                        # semplicemente il massimo discount.
                        score = (
                            discount * 100
                            + max(0, variant["rsi"] - rsi) * 0.10
                            + max(0, rsi - prev_rsi) * 0.05
                        )
                        candidates.append((score, crypto))

                if candidates:
                    candidates.sort(reverse=True)
                    _, crypto = candidates[0]
                    d = ind[crypto]
                    nxt = d.iloc[i + 1]

                    entry = float(nxt["open"])
                    atr = float(d.iloc[i]["atr"])

                    if entry > 0 and atr > 0:
                        position = {
                            "crypto": crypto,
                            "entry": entry,
                            "entry_time": d.index[i + 1],
                            "entry_capital": capital,
                            "atr": atr,
                            "highest": entry,
                            "bars": 0,
                            "entry_discount": float(
                                (d.iloc[i]["sma"] - d.iloc[i]["close"]) / d.iloc[i]["sma"]
                            ),
                        }

                continue

            # ---------- EXIT ----------
            crypto = position["crypto"]
            d = ind[crypto]
            row = d.iloc[i + 1]

            entry = position["entry"]
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
            sma = float(row["sma"]) if pd.notna(row["sma"]) else entry

            position["bars"] += 1
            position["highest"] = max(position["highest"], high)

            stop = entry - position["atr"] * variant["atr_stop"]
            target = entry * (1 + variant["tp"])

            # trailing attivo solo dopo +1.5%.
            trail_active = position["highest"] >= entry * 1.015
            trail = (
                position["highest"] - position["atr"] * 1.2
                if trail_active else -np.inf
            )

            exit_price = None
            reason = None

            # Regola conservativa: se SL e TP sono entrambi toccati
            # nella stessa candela, conta prima lo SL.
            if low <= stop:
                exit_price = stop
                reason = "stop"
            elif high >= target:
                exit_price = target
                reason = "target"
            elif trail_active and low <= trail:
                exit_price = trail
                reason = "trailing"
            elif close >= sma:
                exit_price = close
                reason = "mean"
            elif position["bars"] >= variant["max_hours"]:
                exit_price = close
                reason = "time"

            if exit_price is not None:
                gross_pct = exit_price / entry - 1
                fee_cost = (1 - FEE) * (1 - FEE)
                net_factor = (1 + gross_pct) * fee_cost
                new_capital = position["entry_capital"] * net_factor

                gross_profit_eur = position["entry_capital"] * gross_pct
                fees_eur = position["entry_capital"] * (
                    1 - fee_cost
                ) * (1 + gross_pct)

                net_pct = (new_capital / position["entry_capital"] - 1) * 100

                trades.append({
                    "variant": variant["name"],
                    "crypto": crypto,
                    "entry_time": position["entry_time"],
                    "exit_time": d.index[i + 1],
                    "entry_price": entry,
                    "exit_price": exit_price,
                    "reason": reason,
                    "gross_pct": gross_pct * 100,
                    "net_pct": net_pct,
                    "gross_profit_eur": gross_profit_eur,
                    "fees_eur": fees_eur,
                    "capital_before": position["entry_capital"],
                    "capital_after": new_capital,
                })

                capital = new_capital
                peak_capital = max(peak_capital, capital)
                dd = (capital / peak_capital - 1) * 100
                max_drawdown = min(max_drawdown, dd)

                position = None

        wins = sum(t["net_pct"] > 0 for t in trades)
        losses = sum(t["net_pct"] <= 0 for t in trades)
        total_fees = sum(t["fees_eur"] for t in trades)

        by_reason = {}
        for t in trades:
            by_reason[t["reason"]] = by_reason.get(t["reason"], 0) + 1

        results.append({
            "variant": variant["name"],
            "sma": variant["sma"],
            "dev": f"{variant['dev']*100:.1f}%",
            "RSI": variant["rsi"],
            "trades": len(trades),
            "wins": wins,
            "losses": losses,
            "win_rate": wins / len(trades) * 100 if trades else 0,
            "avg_trade": np.mean([t["net_pct"] for t in trades]) if trades else 0,
            "capital": capital,
            "profitto": capital - initial_capital,
            "profitto_pct": (capital / initial_capital - 1) * 100,
            "commissioni": total_fees,
            "stop": by_reason.get("stop", 0),
            "target": by_reason.get("target", 0),
            "trailing": by_reason.get("trailing", 0),
            "mean": by_reason.get("mean", 0),
            "time": by_reason.get("time", 0),
            "max_drawdown": max_drawdown,
        })

        all_trades.extend(trades)

    return results, pd.DataFrame(all_trades)


st.markdown("---")
st.markdown("**Mean Reversion V8: cerca rimbalzi confermati**")
st.markdown("• Ingresso: deviazione dalla SMA + RSI basso + candela di rimbalzo + filtro volume")
st.markdown("• Uscita: stop ATR + target + ritorno alla media + trailing + time stop")
st.markdown("• Dati: Coinbase Exchange, 1 ora, con validazione di copertura, duplicati e gap")
st.markdown("• Le crypto senza dati completi vengono escluse e il motivo viene mostrato")
