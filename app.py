"""Crypto Bot Simulator — team di agenti + paper trading su dati Coinbase.

SOLO SIMULAZIONE: nessun ordine reale viene mai inviato. Serve per testare
la logica del team di agenti (momentum, mean-reversion, breakout, order-flow)
e la gestione del portafoglio virtuale prima di pensare a qualunque soldo vero.
"""
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from crypto_bot.agents import DEFAULT_AGENTS
from crypto_bot.backtester import run_backtest
from crypto_bot.batch_backtest import fetch_multi_candles, run_batch, run_threshold_sweep
from crypto_bot.data import fetch_candles, VALID_GRANULARITIES
from crypto_bot.feed import LiveFeed
from crypto_bot.live_paper import LivePaperTrader
from crypto_bot.manager import DEFAULT_WEIGHTS, ManagerAgent
from crypto_bot.multi_asset_backtest import run_multi_asset_backtest
from crypto_bot.portfolio import Portfolio

st.set_page_config(page_title="Crypto Bot Simulator", layout="wide")

PRODUCTS = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "LINK-USD", "ADA-USD", "AVAX-USD"]
GRANULARITY_LABELS = {60: "1 minuto", 300: "5 minuti", 900: "15 minuti", 3600: "1 ora"}

st.title("🤖 Crypto Bot Simulator")
st.caption(
    "Simulazione paper-trading (nessun ordine reale) con un team di agenti su dati pubblici Coinbase. "
    "Nota realistica: nessun sistema può garantire di 'battere' il mercato con certezza — qui l'obiettivo "
    "è testare in modo rigoroso se i segnali (trend, ipercomprato/ipervenduto, breakout, order-flow) "
    "hanno un potere predittivo utile, misurando i risultati su dati reali."
)

with st.sidebar:
    st.header("⚙️ Configurazione team di agenti")
    st.caption("Peso di ciascun agente nel voto finale (più alto = più influenza).")
    weights = {}
    for a in DEFAULT_AGENTS:
        weights[a.name] = st.slider(a.name, 0.0, 2.0, DEFAULT_WEIGHTS.get(a.name, 1.0), 0.1)
    buy_th = st.slider("Soglia BUY (score combinato)", 0.0, 1.0, 0.35, 0.05, key="cfg_buy_th")
    sell_th = st.slider("Soglia SELL (score combinato)", -1.0, 0.0, -0.35, 0.05, key="cfg_sell_th")
    st.caption(
        "Non sai che soglia scegliere? Vai su 'Validazione multi-crypto' → "
        "'Confronto soglie' e usa il pulsante che la sceglie in automatico."
    )

    st.divider()
    st.header("💰 Portafoglio virtuale")
    starting_cash = st.number_input("Capitale iniziale ($)", 100.0, 1_000_000.0, 10_000.0, 100.0)
    max_pos_pct = st.slider("Max % capitale per posizione", 5, 100, 20, 5) / 100
    stop_loss_pct = st.slider("Stop-loss %", 0.5, 10.0, 1.5, 0.5) / 100
    take_profit_pct = st.slider("Take-profit %", 0.5, 20.0, 3.0, 0.5) / 100
    fee_pct = st.slider("Commissione per trade %", 0.0, 1.0, 0.6, 0.05) / 100

manager = ManagerAgent(weights=weights, buy_threshold=buy_th, sell_threshold=sell_th)

tab_backtest, tab_batch, tab_auto, tab_live = st.tabs(
    ["📈 Backtest storico", "📊 Validazione multi-crypto", "🎯 Portafoglio automatico", "🔴 Paper trading live"])

# ------------------------------------------------------------------ BACKTEST
with tab_backtest:
    st.subheader("Backtest su candele storiche reali")
    c1, c2, c3 = st.columns(3)
    with c1:
        product = st.selectbox("Crypto", PRODUCTS, key="bt_product")
    with c2:
        granularity = st.selectbox("Timeframe candele", VALID_GRANULARITIES,
                                    format_func=lambda g: GRANULARITY_LABELS.get(g, f"{g}s"),
                                    index=1, key="bt_gran")
    with c3:
        hours = st.slider("Ore di storico", 6, 24 * 14, 48, key="bt_hours")

    if st.button("▶️ Esegui backtest", type="primary"):
        with st.spinner("Scarico candele da Coinbase ed eseguo il backtest..."):
            end = datetime.now(timezone.utc)
            start = end - timedelta(hours=hours)
            try:
                candles = fetch_candles(product, granularity, start, end)
            except Exception as e:
                st.error(f"Errore nello scaricare i dati: {e}")
                candles = pd.DataFrame()

            if candles.empty or len(candles) < 30:
                st.warning("Dati storici insufficienti per questo intervallo/timeframe.")
            else:
                portfolio = Portfolio(starting_cash=starting_cash, fee_rate=fee_pct,
                                       max_position_pct=max_pos_pct, stop_loss_pct=stop_loss_pct,
                                       take_profit_pct=take_profit_pct)
                metrics = run_backtest(candles, manager, portfolio, product)

                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Equity finale", f"${metrics['equity']:,.2f}",
                           f"{metrics['total_return_pct']:+.2f}%")
                m2.metric("Trade chiusi", metrics["num_trades"])
                m3.metric("Win rate", f"{metrics['win_rate_pct']:.1f}%")
                m4.metric("Max drawdown", f"{metrics['max_drawdown_pct']:.2f}%")
                buy_hold = (candles["close"].iloc[-1] / candles["close"].iloc[0] - 1) * 100
                m5.metric("Buy & Hold", f"{buy_hold:+.2f}%")

                eq_df = pd.DataFrame(portfolio.equity_curve).set_index("timestamp")
                st.line_chart(eq_df["equity"], height=280)

                st.markdown("**Prezzo e trade eseguiti**")
                price_chart = candles[["close"]].rename(columns={"close": "prezzo"})
                st.line_chart(price_chart, height=280)

                if portfolio.trade_log:
                    trades_df = pd.DataFrame(portfolio.trade_log)
                    st.dataframe(trades_df, use_container_width=True, hide_index=True)
                    st.download_button("📥 Scarica trade log CSV", trades_df.to_csv(index=False),
                                        f"backtest_{product}_trades.csv", "text/csv")
                else:
                    st.info("Il team di agenti non ha generato nessun trade in questo intervallo.")

# ------------------------------------------------------------- BATCH BACKTEST
with tab_batch:
    st.subheader("Validazione statistica su più crypto")
    st.caption(
        "Un solo backtest su un solo asset/periodo può ingannare (fortuna o overfitting). "
        "Qui il team di agenti viene testato con LE STESSE regole su più crypto insieme: "
        "il win rate aggregato è un numero molto più affidabile di quello di un test singolo."
    )
    batch_products = st.multiselect("Crypto da testare", PRODUCTS, default=PRODUCTS, key="batch_products")
    c1, c2 = st.columns(2)
    with c1:
        batch_gran = st.selectbox("Timeframe candele", VALID_GRANULARITIES,
                                   format_func=lambda g: GRANULARITY_LABELS.get(g, f"{g}s"),
                                   index=1, key="batch_gran")
    with c2:
        batch_hours = st.slider("Ore di storico per ogni crypto", 6, 24 * 14, 72, key="batch_hours")

    if st.button("▶️ Esegui validazione multi-crypto", type="primary"):
        if not batch_products:
            st.warning("Seleziona almeno una crypto.")
        else:
            with st.spinner(f"Backtest su {len(batch_products)} crypto in corso..."):
                portfolio_kwargs = dict(starting_cash=starting_cash, fee_rate=fee_pct,
                                         max_position_pct=max_pos_pct, stop_loss_pct=stop_loss_pct,
                                         take_profit_pct=take_profit_pct)
                manager_kwargs = dict(weights=weights, buy_threshold=buy_th, sell_threshold=sell_th)
                results, trades_df, summary = run_batch(
                    batch_products, batch_gran, batch_hours,
                    manager_kwargs=manager_kwargs, portfolio_kwargs=portfolio_kwargs)

            def fmt_pct(x, sign=False):
                if x is None or x != x:  # NaN check
                    return "n/d"
                return f"{x:+.2f}%" if sign else f"{x:.1f}%"

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Trade chiusi totali", summary["total_closed_trades"])
            m2.metric("Win rate aggregato", fmt_pct(summary["overall_win_rate_pct"]))
            m3.metric("Return medio per crypto", fmt_pct(summary["avg_return_pct"], sign=True))
            m4.metric("Buy & Hold medio", fmt_pct(summary["avg_buy_hold_pct"], sign=True))

            if summary["total_closed_trades"] < 30:
                st.warning(
                    f"Solo {summary['total_closed_trades']} trade chiusi in questo test: campione troppo "
                    "piccolo per fidarsi del win rate. Allunga il periodo di storico o aggiungi più crypto "
                    "prima di trarre conclusioni."
                )

            st.markdown("**Risultati per crypto**")
            st.dataframe(results, use_container_width=True, hide_index=True)

            if not trades_df.empty:
                st.download_button("📥 Scarica tutti i trade CSV", trades_df.to_csv(index=False),
                                    "batch_backtest_trades.csv", "text/csv")

            st.caption(
                "Nota: questo resta un backtest su dati storici recenti, non una garanzia sul futuro. "
                "Un win rate alto ottenuto tarando pesi/soglie proprio su questi stessi dati è un segnale "
                "di overfitting, non di un vero vantaggio — va sempre riverificato su dati nuovi (out-of-sample)."
            )

    st.divider()
    st.subheader("🔍 Confronto soglie (trova il punto di equilibrio)")
    st.caption(
        "Soglia troppo alta → il bot non fa mai trade (troppo prudente). Soglia troppo bassa → "
        "fa trade su segnali deboli/rumore, pagando commissioni e stop-loss frequenti (overtrading). "
        "Qui gli STESSI dati storici vengono testati con più soglie diverse, per vedere dove sta il compromesso."
    )
    if st.button("📈 Confronta soglie su questi dati"):
        if not batch_products:
            st.warning("Seleziona almeno una crypto qui sopra.")
        else:
            with st.spinner(f"Scarico i dati una volta sola e testo 7 soglie diverse su {len(batch_products)} crypto..."):
                candles_by_product = fetch_multi_candles(batch_products, batch_gran, batch_hours)
                portfolio_kwargs = dict(starting_cash=starting_cash, fee_rate=fee_pct,
                                         max_position_pct=max_pos_pct, stop_loss_pct=stop_loss_pct,
                                         take_profit_pct=take_profit_pct)
                thresholds = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]
                sweep_df = run_threshold_sweep(candles_by_product, thresholds, weights=weights,
                                                portfolio_kwargs=portfolio_kwargs)

            st.dataframe(sweep_df, use_container_width=True, hide_index=True)

            if sweep_df["return_medio_pct"].notna().sum() == 0:
                st.error(
                    "Nessuna soglia ha prodotto un risultato utilizzabile: probabilmente il download dei dati "
                    "è fallito per tutte le crypto selezionate (controlla la connessione o riprova più tardi)."
                )
            else:
                chart_df = sweep_df.set_index("soglia")[["win_rate_pct", "return_medio_pct"]]
                st.line_chart(chart_df, height=280)

                min_trades = 10
                usable = sweep_df[sweep_df["return_medio_pct"].notna()]
                candidates = usable[usable["trade_chiusi"] >= min_trades]
                if candidates.empty:
                    candidates = usable
                best_row = candidates.loc[candidates["return_medio_pct"].idxmax()]
                best_th = float(best_row["soglia"])

                st.success(
                    f"🏆 Soglia migliore trovata: **{best_th:.2f}** — return medio "
                    f"{best_row['return_medio_pct']:+.2f}%, win rate {best_row['win_rate_pct']:.1f}%, "
                    f"{int(best_row['trade_chiusi'])} trade chiusi."
                )
                if st.button("✅ Applica questa soglia automaticamente"):
                    st.session_state["cfg_buy_th"] = best_th
                    st.session_state["cfg_sell_th"] = -best_th
                    st.rerun()

                st.caption(
                    "La scelta automatica è basata sui dati appena testati: resta comunque un risultato storico, "
                    "non una garanzia futura. Puoi sempre modificare la soglia a mano dal pannello laterale."
                )

# ----------------------------------------------------------- AUTO PORTFOLIO
with tab_auto:
    st.subheader("Un unico portafoglio, l'agente sceglie da solo la crypto migliore")
    st.caption(
        "A differenza del Backtest storico (una crypto alla volta) o della Validazione multi-crypto "
        "(portafogli separati solo per fare statistica), qui c'è UN SOLO portafoglio condiviso: ad ogni "
        "istante il team di agenti guarda tutte le crypto selezionate insieme e apre una posizione solo "
        "su quella con il segnale più forte — tu scegli l'universo di crypto da seguire, non quale comprare."
    )
    auto_products = st.multiselect("Crypto tra cui l'agente può scegliere", PRODUCTS,
                                    default=PRODUCTS, key="auto_products")
    c1, c2 = st.columns(2)
    with c1:
        auto_gran = st.selectbox("Timeframe candele", VALID_GRANULARITIES,
                                  format_func=lambda g: GRANULARITY_LABELS.get(g, f"{g}s"),
                                  index=1, key="auto_gran")
    with c2:
        auto_hours = st.slider("Ore di storico", 6, 24 * 14, 72, key="auto_hours")

    if st.button("▶️ Esegui backtest a portafoglio unico", type="primary"):
        if len(auto_products) < 2:
            st.warning("Seleziona almeno 2 crypto: con una sola non c'è scelta da fare.")
        else:
            with st.spinner(f"Scarico i dati di {len(auto_products)} crypto e faccio scegliere all'agente..."):
                candles_by_product = fetch_multi_candles(auto_products, auto_gran, auto_hours)
                portfolio = Portfolio(starting_cash=starting_cash, fee_rate=fee_pct,
                                       max_position_pct=max_pos_pct, stop_loss_pct=stop_loss_pct,
                                       take_profit_pct=take_profit_pct)
                try:
                    metrics = run_multi_asset_backtest(candles_by_product, manager, portfolio)
                except ValueError as e:
                    st.error(str(e))
                    metrics = None

            if metrics:
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Equity finale", f"${metrics['equity']:,.2f}", f"{metrics['total_return_pct']:+.2f}%")
                m2.metric("Trade chiusi", metrics["num_trades"])
                m3.metric("Win rate", f"{metrics['win_rate_pct']:.1f}%")
                m4.metric("Max drawdown", f"{metrics['max_drawdown_pct']:.2f}%")

                if portfolio.equity_curve:
                    eq_df = pd.DataFrame(portfolio.equity_curve).set_index("timestamp")
                    st.line_chart(eq_df["equity"], height=280)

                choice_log = metrics.get("choice_log", [])
                if choice_log:
                    st.markdown("**Quale crypto ha scelto l'agente, e quando**")
                    choice_df = pd.DataFrame(choice_log)
                    choice_df["alternative_scartate"] = choice_df["alternative_scartate"].apply(
                        lambda alts: ", ".join(alts) if alts else "—")
                    st.dataframe(choice_df, use_container_width=True, hide_index=True)

                    counts = choice_df["scelta"].value_counts()
                    st.markdown("**Quante volte è stata scelta ciascuna crypto**")
                    st.bar_chart(counts)

                if portfolio.trade_log:
                    trades_df = pd.DataFrame(portfolio.trade_log)
                    st.download_button("📥 Scarica trade log CSV", trades_df.to_csv(index=False),
                                        "portafoglio_automatico_trades.csv", "text/csv")
                else:
                    st.info("Il team di agenti non ha trovato nessuna opportunità in questo intervallo.")

# --------------------------------------------------------------- LIVE PAPER
with tab_live:
    st.subheader("Paper trading in tempo reale (dati live Coinbase, ordini solo simulati)")
    live_products = st.multiselect("Crypto da seguire live", PRODUCTS, default=PRODUCTS[:4], key="live_products")
    bar_seconds = st.select_slider("Durata barra (secondi) — più corta = reazione più rapida",
                                    options=[5, 10, 15, 30, 60], value=15, key="live_bar_seconds")

    if "live_feed" not in st.session_state:
        st.session_state.live_feed = None
    if "live_portfolio" not in st.session_state:
        st.session_state.live_portfolio = None
    if "live_trader" not in st.session_state:
        st.session_state.live_trader = None

    c1, c2, c3 = st.columns(3)
    with c1:
        start_clicked = st.button("🟢 AVVIA SIMULAZIONE LIVE", type="primary", use_container_width=True)
    with c2:
        stop_clicked = st.button("🔴 FERMA", use_container_width=True)
    with c3:
        reset_clicked = st.button("♻️ RESET PORTAFOGLIO", use_container_width=True)

    if start_clicked and live_products:
        feed = LiveFeed(live_products, bar_seconds=bar_seconds)
        feed.start()
        portfolio = Portfolio(starting_cash=starting_cash, fee_rate=fee_pct,
                               max_position_pct=max_pos_pct, stop_loss_pct=stop_loss_pct,
                               take_profit_pct=take_profit_pct)
        st.session_state.live_feed = feed
        st.session_state.live_portfolio = portfolio
        st.session_state.live_trader = LivePaperTrader(feed, manager, portfolio)

    if stop_clicked and st.session_state.live_feed:
        st.session_state.live_feed.stop()

    if reset_clicked and st.session_state.live_portfolio:
        st.session_state.live_portfolio = Portfolio(
            starting_cash=starting_cash, fee_rate=fee_pct, max_position_pct=max_pos_pct,
            stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct)
        if st.session_state.live_trader:
            st.session_state.live_trader.portfolio = st.session_state.live_portfolio

    feed = st.session_state.live_feed
    trader = st.session_state.live_trader
    portfolio = st.session_state.live_portfolio

    if feed is None:
        st.info("Premi 'AVVIA SIMULAZIONE LIVE' per iniziare a ricevere dati reali da Coinbase e far lavorare il team di agenti (nessun ordine reale).")
    else:
        running = feed.is_running()
        status_icons = {"connesso": "🟢", "riconnessione...": "🟡", "errore": "🔴", "fermo": "⚪"}
        status_icon = status_icons.get(feed.status, "🟡" if running else "⚪")
        st.write(f"Stato feed: {status_icon} **{feed.status}**" + (f" — {feed.last_error}" if feed.last_error else ""))

        prices = trader.tick()

        metrics = portfolio.metrics(prices)
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Equity", f"${metrics['equity']:,.2f}", f"{metrics['total_return_pct']:+.2f}%")
        m2.metric("Posizioni aperte", metrics["open_positions"])
        m3.metric("Trade chiusi", metrics["num_trades"])
        m4.metric("Win rate", f"{metrics['win_rate_pct']:.1f}%")
        m5.metric("Cash disponibile", f"${metrics['cash']:,.2f}")

        st.markdown("**🧠 Decisioni del team di agenti (ultimo tick)**")
        rows = []
        for p, d in trader.last_decisions.items():
            rows.append({
                "Crypto": p, "Prezzo": prices.get(p), "Azione": d["action"],
                "Score": round(d.get("score", 0.0), 3),
                "Confidenza": round(d.get("confidence", 0.0), 2),
                "In posizione": p in portfolio.positions,
                "Motivazione": d.get("reason", ""),
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        if portfolio.equity_curve:
            eq_df = pd.DataFrame(portfolio.equity_curve).set_index("timestamp")
            st.line_chart(eq_df["equity"], height=250)

        if portfolio.trade_log:
            st.markdown("**📒 Trade log**")
            trades_df = pd.DataFrame(portfolio.trade_log)
            st.dataframe(trades_df.tail(50), use_container_width=True, hide_index=True)
            st.download_button("📥 Scarica trade log CSV", trades_df.to_csv(index=False),
                                "live_paper_trades.csv", "text/csv")

        if running:
            import time
            time.sleep(2)
            st.rerun()

st.divider()
st.caption(
    "⚠️ Questo strumento è puramente simulativo/educativo: nessun ordine reale viene inviato a Coinbase. "
    "Le performance passate (anche simulate) non garantiscono risultati futuri. Prima di considerare denaro "
    "reale servirebbero: validazione statistica su molti più dati, gestione del rischio più rigorosa e "
    "consapevolezza che la 'latenza a frazioni di secondo' è dominata da trading firms con infrastrutture "
    "dedicate — qui l'obiettivo realistico è reagire più in fretta usando l'order-flow, non batterle sulla latenza pura."
)
