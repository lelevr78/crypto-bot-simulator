import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime, timezone, timedelta

st.set_page_config(page_title="Crypto Bot Simulator", layout="wide")
st.title("🤖 Crypto Trading Bot - Mean Reversion V7")
st.markdown("Strategia V7: mean reversion con conferma di rimbalzo, RSI e stop/target basati sulla volatilità")

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
                headers={"User-Agent": "CryptoBotSimulator/7.0"},
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
    V6: non compra semplicemente una discesa.
    Richiede:
      - prezzo sotto SMA di una certa deviazione;
      - RSI basso;
      - candela di conferma del rimbalzo;
      - volume non anomalo verso il basso.
    Uscite:
      - stop basato su ATR;
      - target iniziale;
      - ritorno verso SMA;
      - trailing dopo un profitto minimo;
      - time stop.
    """

    variants = [
        {"name": "V6_A", "sma": 50, "dev": 0.025, "rsi": 32, "atr_stop": 1.6, "tp": 0.025, "max_hours": 36},
        {"name": "V6_B", "sma": 50, "dev": 0.030, "rsi": 30, "atr_stop": 1.8, "tp": 0.030, "max_hours": 48},
        {"name": "V6_C", "sma": 60, "dev": 0.030, "rsi": 32, "atr_stop": 1.7, "tp": 0.028, "max_hours": 48},
        {"name": "V6_D", "sma": 80, "dev": 0.035, "rsi": 30, "atr_stop": 1.8, "tp": 0.030, "max_hours": 60},
        {"name": "V6_E", "sma": 80, "dev": 0.040, "rsi": 28, "atr_stop": 2.0, "tp": 0.035, "max_hours": 72},
        {"name": "V6_F", "sma": 100, "dev": 0.040, "rsi": 30, "atr_stop": 2.0, "tp": 0.035, "max_hours": 72},
        {"name": "V6_G", "sma": 40, "dev": 0.025, "rsi": 30, "atr_stop": 1.5, "tp": 0.022, "max_hours": 36},
        {"name": "V6_H", "sma": 60, "dev": 0.035, "rsi": 28, "atr_stop": 1.9, "tp": 0.032, "max_hours": 60},
        {"name": "V6_I", "sma": 70, "dev": 0.030, "rsi": 29, "atr_stop": 1.8, "tp": 0.028, "max_hours": 48},
        {"name": "V6_J", "sma": 90, "dev": 0.035, "rsi": 30, "atr_stop": 1.9, "tp": 0.032, "max_hours": 60},
    ]

    results = []

    for variant in variants:
        ind_dict = {}

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

            ind_dict[crypto] = d

        if not ind_dict:
            continue

        # Richiede la stessa timeline per tutti gli asset validi.
        common_index = None
        for d in ind_dict.values():
            common_index = d.index if common_index is None else common_index.intersection(d.index)

        if common_index is None or len(common_index) < variant["sma"] + 40:
            continue

        for crypto in list(ind_dict.keys()):
            ind_dict[crypto] = ind_dict[crypto].loc[common_index]

        num_candles = len(common_index)
        trading_capital = initial_capital
        accantonato = 0.0
        position = None
        trades = []

        start_idx = max(variant["sma"], 30) + 5

        for i in range(start_idx, num_candles - 2):
            if position is None:
                candidates = []

                for crypto, d in ind_dict.items():
                    row = d.iloc[i]
                    prev = d.iloc[i - 1]

                    if not all(pd.notna(row[c]) for c in ["sma", "rsi", "atr", "vol_ma"]):
                        continue

                    price = float(row["close"])
                    sma = float(row["sma"])
                    rsi = float(row["rsi"])
                    atr = float(row["atr"])
                    vol_ma = float(row["vol_ma"])

                    if sma <= 0 or atr <= 0 or vol_ma <= 0:
                        continue

                    discount = (sma - price) / sma

                    # Conferma rimbalzo: la candela attuale chiude sopra
                    # l'apertura e sopra la chiusura precedente.
                    bullish_reversal = (
                        float(row["close"]) > float(row["open"])
                        and float(row["close"]) > float(prev["close"])
                    )

                    # Evita di entrare durante una candela con volume
                    # completamente anomalo rispetto alla media.
                    volume_ok = float(row["volume"]) >= vol_ma * 0.5

                    if (
                        discount >= variant["dev"]
                        and rsi <= variant["rsi"]
                        and bullish_reversal
                        and volume_ok
                    ):
                        candidates.append((discount, crypto))

                if candidates:
                    # Scegliamo il maggiore discount SOLO tra segnali già confermati.
                    candidates.sort(reverse=True)
                    _, best_crypto = candidates[0]

                    d = ind_dict[best_crypto]
                    nxt = d.iloc[i + 1]

                    entry_price = float(nxt["open"])
                    atr_at_entry = float(d.iloc[i]["atr"])

                    if entry_price > 0 and atr_at_entry > 0:
                        position = {
                            "crypto": best_crypto,
                            "entry_price": entry_price,
                            "entry_time": d.index[i + 1],
                            "entry_capital": trading_capital,
                            "entry_sma": float(d.iloc[i]["sma"]),
                            "atr": atr_at_entry,
                            "bars": 0,
                            "highest": entry_price,
                        }

            else:
                crypto = position["crypto"]
                d = ind_dict[crypto]
                row = d.iloc[i + 1]

                entry = position["entry_price"]
                high = float(row["high"])
                low = float(row["low"])
                close = float(row["close"])
                sma = float(row["sma"]) if pd.notna(row["sma"]) else position["entry_sma"]

                position["bars"] += 1
                position["highest"] = max(position["highest"], high)

                # Stop e target sono valutati intrabar, non solo sul close.
                stop_price = entry - position["atr"] * variant["atr_stop"]
                tp_price = entry * (1 + variant["tp"])

                # Dopo +1.5%, protegge parte del guadagno con trailing ATR.
                trail_active = position["highest"] >= entry * 1.015
                trail_price = (
                    position["highest"] - position["atr"] * 1.2
                    if trail_active else -np.inf
                )

                exit_price = None
                exit_reason = None

                if low <= stop_price:
                    exit_price = stop_price
                    exit_reason = "stop"
                elif high >= tp_price:
                    exit_price = tp_price
                    exit_reason = "target"
                elif trail_active and low <= trail_price:
                    exit_price = trail_price
                    exit_reason = "trailing"
                elif close >= sma:
                    exit_price = close
                    exit_reason = "mean"
                elif position["bars"] >= variant["max_hours"]:
                    exit_price = close
                    exit_reason = "time"

                if exit_price is not None:
                    gross = exit_price / entry - 1
                    net_factor = (1 + gross) * (1 - FEE) * (1 - FEE)
                    new_capital = position["entry_capital"] * net_factor

                    net_pct = (new_capital / position["entry_capital"] - 1) * 100

                    trades.append({
                        "net_pct": net_pct,
                        "reason": exit_reason,
                    })

                    trading_capital = new_capital

                    total_capital = trading_capital + accantonato
                    profitto = total_capital - initial_capital

                    # Manteniamo il meccanismo di accantonamento dell'app,
                    # ma calcoliamo la soglia sul profitto totale.
                    if profitto >= th3:
                        da_acc = max(0, (trading_capital - position["entry_capital"]) * a3)
                    elif profitto >= th2:
                        da_acc = max(0, (trading_capital - position["entry_capital"]) * a2)
                    elif profitto >= th1:
                        da_acc = max(0, (trading_capital - position["entry_capital"]) * a1)
                    else:
                        da_acc = 0

                    if da_acc > 0:
                        accantonato += da_acc
                        trading_capital -= da_acc

                    position = None

        total_capital = trading_capital + accantonato
        profitto = total_capital - initial_capital
        profitto_pct = (profitto / initial_capital) * 100

        num_trades = len(trades)
        wins = sum(1 for t in trades if t["net_pct"] > 0)
        win_rate = wins / num_trades * 100 if num_trades else 0

        avg_trade = (
            float(np.mean([t["net_pct"] for t in trades]))
            if trades else 0
        )

        results.append({
            "variant": variant["name"],
            "sma": variant["sma"],
            "dev": f"{variant['dev']*100:.1f}%",
            "RSI": variant["rsi"],
            "trades": num_trades,
            "wins": wins,
            "win_rate": win_rate,
            "avg_trade": avg_trade,
            "capital": total_capital,
            "profitto": profitto,
            "profitto_pct": profitto_pct,
        })

    return results


st.markdown(f"**Capitale:** €{initial_capital} | **Giorni:** {days} | **Crypto:** {len(TOP_CRYPTOS)}")

if st.button("▶️ Esegui Mean Reversion V7", key="simulate"):
    st.info("⏳ Download e validazione dati Coinbase Exchange...")

    data_dict = {}
    errors = {}
    progress = st.progress(0)
    status = st.empty()

    for idx, crypto in enumerate(TOP_CRYPTOS):
        status.write(f"Scarico e verifico **{crypto}** — {idx + 1}/{len(TOP_CRYPTOS)}")
        try:
            df, fetch_error = fetch_candles(crypto, days)
            if df is not None:
                data_dict[crypto] = df
            else:
                errors[crypto] = fetch_error or "errore sconosciuto"
        except Exception as e:
            errors[crypto] = f"errore inatteso: {type(e).__name__}: {e}"

        progress.progress((idx + 1) / len(TOP_CRYPTOS))

    progress.empty()
    status.empty()

    st.subheader("📡 Risultato download")

    if data_dict:
        st.success(f"✅ {len(data_dict)}/{len(TOP_CRYPTOS)} crypto valide")

        coverage = []
        for crypto, df in data_dict.items():
            coverage.append({
                "Crypto": crypto,
                "Candele": len(df),
                "Prima": df.index[0].strftime("%Y-%m-%d %H:%M UTC"),
                "Ultima": df.index[-1].strftime("%Y-%m-%d %H:%M UTC"),
            })

        st.dataframe(
            pd.DataFrame(coverage).sort_values("Crypto"),
            use_container_width=True,
            hide_index=True,
        )

        if errors:
            with st.expander(f"⚠️ {len(errors)} crypto non valide — mostra motivi"):
                for crypto in TOP_CRYPTOS:
                    if crypto in errors:
                        st.write(f"❌ **{crypto}** — {errors[crypto]}")

        st.info("🔍 Avvio backtest V7 sulle sole crypto con dataset completo e validato.")

        with st.spinner("Analisi delle 10 varianti V7..."):
            results = backtest_mean_reversion(
                data_dict,
                initial_capital,
                threshold1, acc1,
                threshold2, acc2,
                threshold3, acc3,
            )

        if results:
            df_res = pd.DataFrame(results)

            # Non presenta una variante come "migliore" in modo assoluto:
            # mostra semplicemente la tabella completa per il periodo testato.
            st.subheader("📊 Risultati V7 — periodo selezionato")

            display = df_res[
                ["variant", "sma", "dev", "RSI", "trades",
                 "win_rate", "avg_trade", "profitto", "profitto_pct"]
            ].copy()

            display.columns = [
                "Strategia", "SMA", "Deviation", "RSI", "Trade",
                "Win %", "Media/trade %", "Profitto €", "Profitto %"
            ]

            st.dataframe(display, use_container_width=True, hide_index=True)

            st.caption(
                "I risultati sono riferiti esclusivamente al periodo selezionato "
                "e non costituiscono una previsione dei risultati futuri."
            )

            csv = df_res.to_csv(index=False)
            st.download_button(
                label="📥 Scarica risultati CSV",
                data=csv,
                file_name=f"mean_reversion_v7_{days}d.csv",
                mime="text/csv",
            )
        else:
            st.error("❌ Nessun risultato di backtest prodotto.")
    else:
        st.error("❌ Nessuna crypto ha superato la validazione.")
        with st.expander("Dettaglio degli errori"):
            for crypto, reason in errors.items():
                st.write(f"❌ **{crypto}** — {reason}")


st.markdown("---")
st.markdown("**Mean Reversion V7: cerca rimbalzi confermati**")
st.markdown("• Ingresso: deviazione dalla SMA + RSI basso + candela di rimbalzo + filtro volume")
st.markdown("• Uscita: stop ATR + target + ritorno alla media + trailing + time stop")
st.markdown("• Dati: Coinbase Exchange, 1 ora, con validazione di copertura, duplicati e gap")
st.markdown("• Le crypto senza dati completi vengono escluse e il motivo viene mostrato")
