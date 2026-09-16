import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime, timezone, timedelta

st.set_page_config(page_title="Crypto Bot Simulator", layout="wide")
st.title("🤖 Crypto Trading Bot - Mean Reversion V12")
st.success("🟢 VERSIONE V12 CARICATA — FILE DI TEST CORRETTO")
st.write("Se stai vedendo questa scritta, l'app sta eseguendo **app crypto bot v12.py**.")
st.caption("BUILD V12 · Coinbase Exchange · 120 giorni · 1 ora")

# COMANDO PRINCIPALE V12 — deve essere visibile subito sotto il marker.
if "start_v12" not in st.session_state:
    st.session_state["start_v12"] = False

def _start_v12():
    st.session_state["start_v12"] = True

st.button(
    "🚀 AVVIA SIMULAZIONE V12",
    type="primary",
    use_container_width=True,
    on_click=_start_v12,
    key="start_v12_button",
)

run_simulation = st.session_state["start_v12"]
st.caption("🧪 V12: ingresso meno restrittivo — setup + candela verde + almeno 2 conferme su 4.")
st.caption("⬆️ Questo è il pulsante della V12. Se non compare, il deploy NON sta eseguendo questo file.")

st.markdown("Strategia V12: mean reversion con conferma di rimbalzo, RSI e stop/target basati sulla volatilità")

st.caption("Premi il pulsante qui sopra per scaricare i dati Coinbase e avviare il backtest.")

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
                headers={"User-Agent": "CryptoBotSimulator/9.0"},
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
    V12 - Mean Reversion con conferma di inversione.

    Non usa accantonamenti: il capitale misura solo la strategia.
    L'ingresso richiede:
      1) oversold (RSI basso + deviazione dalla SMA);
      2) conferma dell'inversione su più segnali;
      3) filtro di trend per evitare di comprare durante forti ribassi;
      4) cooldown per evitare re-entry immediati dopo uno stop.

    Le 10 varianti servono per confrontare parametri diversi sul periodo
    selezionato; non sono una previsione dei risultati futuri.
    """

    variants = [
        {"name": "V12_A", "sma": 50, "dev": .025, "rsi": 34, "confirm": .003, "atr_stop": 1.7, "tp": .025, "max_hours": 48, "cooldown": 8},
        {"name": "V12_B", "sma": 60, "dev": .025, "rsi": 33, "confirm": .004, "atr_stop": 1.8, "tp": .028, "max_hours": 48, "cooldown": 10},
        {"name": "V12_C", "sma": 70, "dev": .030, "rsi": 32, "confirm": .004, "atr_stop": 1.8, "tp": .030, "max_hours": 60, "cooldown": 10},
        {"name": "V12_D", "sma": 80, "dev": .030, "rsi": 33, "confirm": .005, "atr_stop": 1.9, "tp": .030, "max_hours": 60, "cooldown": 12},
        {"name": "V12_E", "sma": 80, "dev": .035, "rsi": 31, "confirm": .005, "atr_stop": 1.9, "tp": .032, "max_hours": 72, "cooldown": 12},
        {"name": "V12_F", "sma": 100, "dev": .035, "rsi": 32, "confirm": .005, "atr_stop": 2.0, "tp": .035, "max_hours": 72, "cooldown": 14},
        {"name": "V12_G", "sma": 60, "dev": .030, "rsi": 31, "confirm": .003, "atr_stop": 1.9, "tp": .030, "max_hours": 60, "cooldown": 12},
        {"name": "V12_H", "sma": 90, "dev": .035, "rsi": 32, "confirm": .004, "atr_stop": 2.0, "tp": .035, "max_hours": 72, "cooldown": 14},
        {"name": "V12_I", "sma": 70, "dev": .035, "rsi": 30, "confirm": .004, "atr_stop": 2.0, "tp": .035, "max_hours": 72, "cooldown": 14},
        {"name": "V12_J", "sma": 100, "dev": .040, "rsi": 30, "confirm": .005, "atr_stop": 2.1, "tp": .040, "max_hours": 96, "cooldown": 16},
    ]

    results = []
    all_trades = []

    for variant in variants:
        ind = {}

        for crypto, df in data_dict.items():
            if df is None or len(df) <= variant["sma"] + 40:
                continue

            d = df.copy()
            d["sma"] = d["close"].rolling(variant["sma"]).mean()
            d["sma_fast"] = d["close"].rolling(20).mean()

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
            d["rsi_delta"] = d["rsi"].diff()

            # MACD semplificato.
            ema12 = d["close"].ewm(span=12, adjust=False).mean()
            ema26 = d["close"].ewm(span=26, adjust=False).mean()
            d["macd"] = ema12 - ema26
            d["macd_signal"] = d["macd"].ewm(span=9, adjust=False).mean()

            ind[crypto] = d

        if not ind:
            continue

        common_index = None
        for d in ind.values():
            common_index = d.index if common_index is None else common_index.intersection(d.index)

        if common_index is None or len(common_index) < variant["sma"] + 50:
            continue

        for crypto in list(ind.keys()):
            ind[crypto] = ind[crypto].loc[common_index]

        capital = float(initial_capital)
        position = None
        cooldown_until = {crypto: -10**9 for crypto in ind}
        trades = []
        peak_capital = capital
        max_drawdown = 0.0

        first_i = max(variant["sma"], 100) + 5

        for i in range(first_i, len(common_index) - 2):

            # ================= ENTRY =================
            if position is None:
                candidates = []
                near_misses = []

                for crypto, d in ind.items():
                    if i < cooldown_until.get(crypto, -10**9):
                        continue

                    row = d.iloc[i]
                    prev = d.iloc[i - 1]
                    prev2 = d.iloc[i - 2]

                    needed = ["sma", "sma_fast", "rsi", "atr", "vol_ma", "macd", "macd_signal"]
                    if not all(pd.notna(row[c]) for c in needed):
                        continue
                    if not all(pd.notna(prev[c]) for c in ["rsi", "close", "high", "macd", "macd_signal"]):
                        continue
                    if not all(pd.notna(prev2[c]) for c in ["rsi", "close"]):
                        continue

                    close = float(row["close"])
                    open_price = float(row["open"])
                    prev_close_val = float(prev["close"])
                    prev2_close_val = float(prev2["close"])
                    sma = float(row["sma"])
                    sma_fast = float(row["sma_fast"])
                    rsi = float(row["rsi"])
                    prev_rsi = float(prev["rsi"])
                    prev2_rsi = float(prev2["rsi"])
                    atr = float(row["atr"])
                    vol_ma = float(row["vol_ma"])
                    volume = float(row["volume"])
                    macd = float(row["macd"])
                    macd_signal = float(row["macd_signal"])
                    prev_macd = float(prev["macd"])
                    prev_signal = float(prev["macd_signal"])

                    if sma <= 0 or atr <= 0 or vol_ma <= 0:
                        continue

                    discount = (sma - close) / sma

                    # 1) Oversold.
                    setup = discount >= variant["dev"] and rsi <= variant["rsi"]

                    # 2) Il minimo recente non deve continuare a fare nuovi minimi:
                    # la candela attuale chiude sopra quella precedente e sopra l'apertura.
                    bullish = close > open_price and close > prev_close_val

                    # 3) RSI deve migliorare per almeno due osservazioni.
                    rsi_reversal = rsi > prev_rsi >= prev2_rsi

                    # 4) Prezzo deve recuperare almeno una piccola parte della deviazione.
                    recovery = (close - prev2_close_val) / prev2_close_val >= variant["confirm"]

                    # 5) MACD deve essere in miglioramento; non serve ancora che
                    # sia completamente positivo, evitando di entrare troppo tardi.
                    macd_improving = macd > prev_macd and macd >= macd_signal * 0.995

                    # 6) Filtro trend: niente acquisto se la media veloce
                    # è in forte discesa rispetto alla candela precedente.
                    trend_ok = float(row["sma_fast"]) >= float(prev["sma_fast"]) * 0.998

                    volume_ok = volume >= vol_ma * 0.6

                    # V12: setup + candela di inversione obbligatori.
                    # Poi servono almeno 2 conferme su 4:
                    # RSI, recovery, MACD, volume/trend.
                    confirmations = sum([
                        bool(rsi_reversal),
                        bool(recovery),
                        bool(macd_improving),
                        bool(volume_ok and trend_ok),
                    ])

                    if setup and bullish and confirmations >= 2:
                        # Score basato sulla qualità della conferma,
                        # non solo sulla distanza dalla SMA.
                        score = (
                            confirmations * 10
                            + discount * 100
                            + max(0, rsi - prev2_rsi) * 0.10
                            + max(0, recovery) * 100
                        )
                        candidates.append((score, crypto))

                if candidates:
                    candidates.sort(reverse=True)
                    _, crypto = candidates[0]
                    d = ind[crypto]

                    # Ingresso sulla candela successiva al segnale.
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
                            "signal_time": d.index[i],
                        }

                continue

            # ================= EXIT =================
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

            trail_active = position["highest"] >= entry * 1.018
            trail = (
                position["highest"] - position["atr"] * 1.15
                if trail_active else -np.inf
            )

            exit_price = None
            reason = None

            # Regola conservativa: SL prima del TP se entrambi sono toccati.
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
                fee_factor = (1 - FEE) * (1 - FEE)
                new_capital = position["entry_capital"] * (1 + gross_pct) * fee_factor

                gross_profit_eur = position["entry_capital"] * gross_pct
                fees_eur = position["entry_capital"] * (1 + gross_pct) * (1 - fee_factor)
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
                max_drawdown = min(max_drawdown, (capital / peak_capital - 1) * 100)

                # Cooldown dopo ogni stop; più importante dopo una perdita.
                if reason == "stop":
                    cooldown_until[crypto] = i + 1 + variant["cooldown"]
                else:
                    cooldown_until[crypto] = i + 1 + max(4, variant["cooldown"] // 2)

                position = None

        wins = sum(t["net_pct"] > 0 for t in trades)
        losses = sum(t["net_pct"] <= 0 for t in trades)
        gross_wins = sum(max(0, t["gross_profit_eur"]) for t in trades)
        gross_losses = abs(sum(min(0, t["gross_profit_eur"]) for t in trades))
        profit_factor = gross_wins / gross_losses if gross_losses > 0 else np.inf
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
            "profit_factor": profit_factor,
            "stop": by_reason.get("stop", 0),
            "target": by_reason.get("target", 0),
            "trailing": by_reason.get("trailing", 0),
            "mean": by_reason.get("mean", 0),
            "time": by_reason.get("time", 0),
            "max_drawdown": max_drawdown,
        })

        all_trades.extend(trades)

    return results, pd.DataFrame(all_trades)



# ===================== AVVIO SIMULAZIONE =====================
if run_simulation:
    st.success("🟢 PULSANTE V12 RICEVUTO — LA SIMULAZIONE È PARTITA")
    st.info("⏳ Sto scaricando e validando i dati Coinbase Exchange...")
    data_dict = {}
    errors = {}

    progress = st.progress(0)
    status = st.empty()

    for idx, crypto in enumerate(TOP_CRYPTOS):
        status.write(f"Scarico **{crypto}** — {idx + 1}/{len(TOP_CRYPTOS)}")
        try:
            df, error = fetch_candles(crypto, days)
            if df is not None and len(df) > 0:
                data_dict[crypto] = df
            else:
                errors[crypto] = error or "Dati non validi o insufficienti."
        except Exception as exc:
            errors[crypto] = f"{type(exc).__name__}: {exc}"

        progress.progress((idx + 1) / len(TOP_CRYPTOS))

    progress.empty()
    status.empty()

    st.subheader("🔎 Validazione dati")

    if data_dict:
        st.success(f"✅ {len(data_dict)} crypto valide su {len(TOP_CRYPTOS)}")

        coverage_rows = []
        for crypto, df in data_dict.items():
            coverage_rows.append({
                "Crypto": crypto,
                "Candele": len(df),
                "Prima": df.index[0].strftime("%Y-%m-%d %H:%M UTC"),
                "Ultima": df.index[-1].strftime("%Y-%m-%d %H:%M UTC"),
            })

        st.dataframe(
            pd.DataFrame(coverage_rows).sort_values("Crypto"),
            use_container_width=True,
            hide_index=True,
        )

        if errors:
            with st.expander(f"⚠️ {len(errors)} crypto escluse — mostra motivi"):
                for crypto, error in errors.items():
                    st.write(f"❌ **{crypto}** — {error}")

        st.subheader("📈 Backtest V12")

        with st.spinner("Calcolo delle 10 varianti V12..."):
            results, trades_df = backtest_mean_reversion(
                data_dict,
                initial_capital,
                threshold1, acc1,
                threshold2, acc2,
                threshold3, acc3,
            )

        if results:
            result_df = pd.DataFrame(results)

            shown = result_df[
                [
                    "variant", "sma", "dev", "RSI", "trades", "wins", "losses",
                    "win_rate", "avg_trade", "capital", "profitto",
                    "profitto_pct", "commissioni", "profit_factor",
                    "stop", "target", "trailing", "mean", "time",
                    "max_drawdown"
                ]
            ].copy()

            shown.columns = [
                "Strategia", "SMA", "Dev.", "RSI", "Trade", "Win", "Loss",
                "Win %", "Media/trade %", "Capitale finale €",
                "Profitto €", "Profitto %", "Commissioni €", "Profit Factor",
                "Stop", "Target", "Trailing", "Mean", "Time", "Max DD %"
            ]

            st.dataframe(shown, use_container_width=True, hide_index=True)

            if not trades_df.empty:
                st.subheader("📋 Operazioni")
                st.dataframe(
                    trades_df.sort_values(["variant", "entry_time"]),
                    use_container_width=True,
                    hide_index=True,
                )

                st.download_button(
                    "📥 Scarica operazioni V12 CSV",
                    data=trades_df.to_csv(index=False),
                    file_name=f"crypto_bot_v12_trades_{int(days)}d.csv",
                    mime="text/csv",
                )

            st.download_button(
                "📥 Scarica risultati V12 CSV",
                data=result_df.to_csv(index=False),
                file_name=f"crypto_bot_v12_results_{int(days)}d.csv",
                mime="text/csv",
            )

            st.caption(
                "Risultati riferiti esclusivamente al periodo storico selezionato. "
                "Il backtest non garantisce risultati futuri."
            )
        else:
            st.error("❌ Nessun risultato di backtest prodotto.")
    else:
        st.error("❌ Nessuna crypto ha superato la validazione.")
        with st.expander("Dettaglio errori"):
            for crypto, error in errors.items():
                st.write(f"❌ **{crypto}** — {error}")


st.markdown("---")
st.markdown("**Mean Reversion V12 — ingresso solo dopo conferma di inversione**")
st.markdown("• Oversold: deviazione SMA + RSI basso")
st.markdown("• Conferma: candela positiva + RSI in miglioramento + recupero + MACD")
st.markdown("• Filtro trend e cooldown dopo stop per ridurre re-entry durante ribassi")
st.markdown("• Uscite: stop ATR + target + trailing + ritorno alla media + time stop")
st.markdown("• Dati: Coinbase Exchange, 1 ora, con validazione completa")
