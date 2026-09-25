"""Crypto Bot Simulator — team di agenti + paper trading su dati Coinbase.

SOLO SIMULAZIONE: nessun ordine reale viene mai inviato. Serve per testare
la logica del team di agenti (momentum, mean-reversion, breakout, order-flow)
e la gestione del portafoglio virtuale prima di pensare a qualunque soldo vero.
"""
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from crypto_bot.agents import DEFAULT_AGENTS
from crypto_bot.auto_recalibration import recalibrate
from crypto_bot.batch_backtest import fetch_multi_candles
from crypto_bot.data import VALID_GRANULARITIES
from crypto_bot.feed import LiveFeed
from crypto_bot.live_paper import LivePaperTrader
from crypto_bot.manager import DEFAULT_WEIGHTS, WEIGHT_PROFILES, ManagerAgent
from crypto_bot.multi_asset_backtest import run_multi_asset_backtest, run_walk_forward
from crypto_bot.multi_asset_backtest import run_threshold_sweep as run_multi_asset_sweep
from crypto_bot.portfolio import Portfolio
from polymarket_monitor.arbitrage import ArbitrageConfig, ArbitrageMonitor
from polymarket_monitor.clob_api import best_bid_ask, fetch_books_batch
from polymarket_monitor.gamma_api import fetch_active_crypto_markets

st.set_page_config(page_title="Crypto Bot Simulator", layout="wide")

PRODUCTS = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "LINK-USD", "ADA-USD", "AVAX-USD"]
GRANULARITY_LABELS = {60: "1 minuto", 300: "5 minuti", 900: "15 minuti", 3600: "1 ora"}


def keep_screen_awake():
    """Impedisce allo schermo del telefono di bloccarsi durante un download lungo
    (Screen Wake Lock API — supportata da Safari iOS 16.4+ e dai browser Android
    recenti). Se il browser non la supporta, non succede nulla di rotto: il
    download prosegue comunque, semplicemente lo schermo potrà bloccarsi come prima."""
    components.html(
        """
        <script>
        (async () => {
            try {
                if ('wakeLock' in navigator) {
                    await navigator.wakeLock.request('screen');
                }
            } catch (e) {}
        })();
        </script>
        """,
        height=0,
    )

st.title("🤖 Crypto Bot Simulator")
st.caption(
    "Simulazione paper-trading (nessun ordine reale) con un team di agenti su dati pubblici Coinbase. "
    "Nota realistica: nessun sistema può garantire di 'battere' il mercato con certezza — qui l'obiettivo "
    "è testare in modo rigoroso se i segnali (trend, ipercomprato/ipervenduto, breakout, order-flow) "
    "hanno un potere predittivo utile, misurando i risultati su dati reali."
)

with st.sidebar:
    st.header("⚙️ Configurazione")
    with st.expander("Pesi agenti, soglie e portafoglio", expanded=False):
        st.caption("Peso di ciascun agente nel voto finale (più alto = più influenza).")
        weights = {}
        for a in DEFAULT_AGENTS:
            weights[a.name] = st.slider(a.name, 0.0, 2.0, DEFAULT_WEIGHTS.get(a.name, 1.0), 0.1,
                                         key=f"cfg_weight_{a.name}")
        st.caption(
            "Non sai come pesarli? Vai su 'Portafoglio automatico' → 'Walk-forward' e usa il "
            "pulsante che sceglie il mix di pesi migliore in automatico, verificato su dati mai visti."
        )
        buy_th = st.slider("Soglia BUY (score combinato)", 0.0, 1.0, 0.35, 0.05, key="cfg_buy_th")
        sell_th = st.slider("Soglia SELL (score combinato)", -1.0, 0.0, -0.35, 0.05, key="cfg_sell_th")
        st.caption(
            "Non sai che soglia scegliere? Vai su 'Portafoglio automatico' → "
            "'Confronto soglie' e usa il pulsante che la sceglie in automatico."
        )

        st.divider()
        starting_cash = st.number_input("Capitale iniziale ($)", 100.0, 1_000_000.0, 10_000.0, 100.0)
        max_pos_pct = st.slider("Max % capitale per posizione", 5, 100, 20, 5) / 100
        stop_loss_pct = st.slider("Stop-loss %", 0.5, 10.0, 1.5, 0.5) / 100
        take_profit_pct = st.slider("Take-profit %", 0.5, 20.0, 3.0, 0.5) / 100
        fee_pct = st.slider("Commissione per trade %", 0.0, 1.0, 0.6, 0.05) / 100
        min_hold_minutes = st.slider(
            "Holding minimo prima di uscire per segnale (minuti)", 0, 1440, 60, 15,
            key="cfg_min_hold",
            help="Lo stop-loss e il take-profit restano SEMPRE immediati. Questo vincolo si applica "
                 "solo alle uscite decise dagli agenti, per evitare trade-lampo la cui commissione "
                 "supera il guadagno atteso. 0 = nessun vincolo (comportamento precedente)."
        )

manager = ManagerAgent(weights=weights, buy_threshold=buy_th, sell_threshold=sell_th)

tab_auto, tab_live, tab_poly = st.tabs(
    ["🎯 Portafoglio automatico", "🔴 Paper trading live", "🎲 Polymarket arbitraggio"])

# ----------------------------------------------------------- AUTO PORTFOLIO
with tab_auto:
    st.subheader("Un unico portafoglio, l'agente sceglie da solo la crypto migliore")
    st.caption(
        "UN SOLO portafoglio condiviso: ad ogni istante il team di agenti guarda tutte le crypto "
        "selezionate insieme e apre una posizione solo su quella con il segnale più forte — tu scegli "
        "l'universo di crypto da seguire, non quale comprare."
    )
    auto_products = st.multiselect("Crypto tra cui l'agente può scegliere", PRODUCTS,
                                    default=PRODUCTS, key="auto_products")
    c1, c2 = st.columns(2)
    with c1:
        auto_gran = st.selectbox("Timeframe candele", VALID_GRANULARITIES,
                                  format_func=lambda g: GRANULARITY_LABELS.get(g, f"{g}s"),
                                  index=1, key="auto_gran")
    with c2:
        auto_hours = st.slider("Ore di storico", 6, 24 * 180, 72, key="auto_hours")

    if st.button("▶️ Esegui backtest a portafoglio unico", type="primary"):
        if len(auto_products) < 2:
            st.warning("Seleziona almeno 2 crypto: con una sola non c'è scelta da fare.")
        else:
            with st.spinner(f"Scarico i dati di {len(auto_products)} crypto e faccio scegliere all'agente..."):
                keep_screen_awake()
                candles_by_product = fetch_multi_candles(auto_products, auto_gran, auto_hours)
                portfolio = Portfolio(starting_cash=starting_cash, fee_rate=fee_pct,
                                       max_position_pct=max_pos_pct, stop_loss_pct=stop_loss_pct,
                                       take_profit_pct=take_profit_pct, min_hold_minutes=min_hold_minutes)
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

                candidate_counts = metrics.get("candidate_counts", {})
                chosen_counts = metrics.get("chosen_counts", {})
                if candidate_counts:
                    st.markdown("**Quanto ha pesato ciascuna crypto nella scelta**")
                    st.caption(
                        "'Segnali validi' = quante volte ha superato la soglia BUY. 'Scelta' = quante "
                        "volte ha AVUTO il punteggio più alto tra i segnali validi in quel momento. Una "
                        "crypto con tanti segnali validi ma pochissime scelte perde sempre il confronto "
                        "con le altre, non è che 'non funziona mai'."
                    )
                    counts_df = pd.DataFrame({
                        "Crypto": list(candidate_counts.keys()),
                        "Segnali validi": list(candidate_counts.values()),
                        "Scelta": [chosen_counts.get(p, 0) for p in candidate_counts],
                    }).sort_values("Segnali validi", ascending=False)
                    st.dataframe(counts_df, use_container_width=True, hide_index=True)
                    st.bar_chart(counts_df.set_index("Crypto")[["Segnali validi", "Scelta"]])

                choice_log = metrics.get("choice_log", [])
                if choice_log:
                    with st.expander("Dettaglio di ogni scelta (quando e perché)"):
                        choice_df = pd.DataFrame(choice_log)
                        choice_df["alternative_scartate"] = choice_df["alternative_scartate"].apply(
                            lambda alts: ", ".join(alts) if alts else "—")
                        st.dataframe(choice_df, use_container_width=True, hide_index=True)

                if portfolio.trade_log:
                    trades_df = pd.DataFrame(portfolio.trade_log)
                    st.download_button("📥 Scarica trade log CSV", trades_df.to_csv(index=False),
                                        "portafoglio_automatico_trades.csv", "text/csv")
                else:
                    st.info("Il team di agenti non ha trovato nessuna opportunità in questo intervallo.")

    st.divider()
    st.subheader("🔍 Confronto soglie per il portafoglio unico")
    st.caption(
        "Qui la soglia va tarata a parte rispetto al Backtest storico su una crypto sola: guardando più "
        "crypto insieme, basta che UNA superi la soglia per far scattare un trade, quindi le occasioni "
        "(e il rumore) si moltiplicano. Di solito qui serve una soglia più alta."
    )
    if st.button("📈 Confronta soglie sul portafoglio unico"):
        if len(auto_products) < 2:
            st.warning("Seleziona almeno 2 crypto qui sopra.")
        else:
            with st.spinner(f"Scarico i dati una volta sola e testo 7 soglie diverse su {len(auto_products)} crypto..."):
                keep_screen_awake()
                candles_by_product = fetch_multi_candles(auto_products, auto_gran, auto_hours)
                portfolio_kwargs = dict(starting_cash=starting_cash, fee_rate=fee_pct,
                                         max_position_pct=max_pos_pct, stop_loss_pct=stop_loss_pct,
                                         take_profit_pct=take_profit_pct, min_hold_minutes=min_hold_minutes)
                thresholds = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50]
                sweep_df = run_multi_asset_sweep(candles_by_product, thresholds, weights=weights,
                                                  portfolio_kwargs=portfolio_kwargs)

            st.dataframe(sweep_df, use_container_width=True, hide_index=True)

            if sweep_df["return_pct"].notna().sum() == 0:
                st.error(
                    "Nessuna soglia ha prodotto un risultato utilizzabile: probabilmente il download dei "
                    "dati è fallito per tutte le crypto selezionate."
                )
            else:
                chart_df = sweep_df.set_index("soglia")[["win_rate_pct", "return_pct"]]
                st.line_chart(chart_df, height=280)

                min_trades = 10
                usable = sweep_df[sweep_df["return_pct"].notna()]
                candidates = usable[usable["trade_chiusi"] >= min_trades]
                if candidates.empty:
                    candidates = usable
                best_row = candidates.loc[candidates["return_pct"].idxmax()]
                best_th = float(best_row["soglia"])

                st.success(
                    f"🏆 Soglia migliore trovata: **{best_th:.2f}** — return "
                    f"{best_row['return_pct']:+.2f}%, win rate {best_row['win_rate_pct']:.1f}%, "
                    f"{int(best_row['trade_chiusi'])} trade chiusi."
                )
                if st.button("✅ Applica questa soglia automaticamente", key="apply_auto_th"):
                    st.session_state["cfg_buy_th"] = best_th
                    st.session_state["cfg_sell_th"] = -best_th
                    st.rerun()

    st.divider()
    st.subheader("🔬 Walk-forward (taratura + verifica separate)")
    st.caption(
        "Il test più rigoroso contro l'overfitting: soglia, holding minimo E il mix di pesi tra "
        "gli agenti vengono scelti SOLO guardando la prima parte dello storico (in-sample). Il "
        "risultato finale che conta è quello sulla parte successiva, mai vista durante la taratura "
        "(out-of-sample) — se regge vicino ai numeri dell'in-sample è un segnale vero, se crolla "
        "era solo rumore tarato bene."
    )
    split_pct = st.select_slider("Percentuale dati per la taratura (in-sample)",
                                  options=[50, 60, 70], value=60, key="wf_split_pct")
    if st.button("🔬 Esegui walk-forward"):
        if len(auto_products) < 2:
            st.warning("Seleziona almeno 2 crypto qui sopra.")
        else:
            with st.spinner(f"Scarico i dati una volta sola, taro su {split_pct}% dello storico "
                             f"(soglia, holding e pesi) e verifico sul resto..."):
                keep_screen_awake()
                candles_by_product = fetch_multi_candles(auto_products, auto_gran, auto_hours)
                portfolio_kwargs = dict(starting_cash=starting_cash, fee_rate=fee_pct,
                                         max_position_pct=max_pos_pct, stop_loss_pct=stop_loss_pct,
                                         take_profit_pct=take_profit_pct)
                thresholds = [0.15, 0.20, 0.25, 0.30, 0.35]
                min_holds = [240, 480, 720, 1440]
                try:
                    wf = run_walk_forward(candles_by_product, thresholds, min_holds, weights=weights,
                                           weight_profiles=WEIGHT_PROFILES,
                                           portfolio_kwargs=portfolio_kwargs, split_ratio=split_pct / 100)
                except ValueError as e:
                    st.error(str(e))
                    wf = None

            if wf:
                st.info(
                    f"Combinazione scelta sull'in-sample: soglia **{wf['best_threshold']:.2f}**, "
                    f"holding minimo **{int(wf['best_min_hold'])} min**, pesi "
                    f"**\"{wf['best_weight_profile']}\"** ({wf['best_weights']}). "
                    f"Punto di taglio: {wf['split_timestamp']}."
                )
                if st.button("✅ Applica soglia, holding e pesi automaticamente", key="apply_wf_all"):
                    st.session_state["cfg_buy_th"] = wf["best_threshold"]
                    st.session_state["cfg_sell_th"] = -wf["best_threshold"]
                    st.session_state["cfg_min_hold"] = int(wf["best_min_hold"])
                    for agent_name, w in wf["best_weights"].items():
                        st.session_state[f"cfg_weight_{agent_name}"] = w
                    st.rerun()

                is_m, oos_m = wf["is_metrics"], wf["oos_metrics"]
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**In-sample (taratura)**")
                    st.metric("Return", f"{is_m['return_pct']:+.2f}%")
                    st.metric("Win rate", f"{is_m['win_rate_pct']:.1f}%")
                    st.metric("Trade", int(is_m["trade"]))
                    st.metric("Max drawdown", f"{is_m['drawdown_pct']:.2f}%")
                with c2:
                    st.markdown("**Out-of-sample (verifica, mai vista prima)**")
                    st.metric("Return", f"{oos_m['total_return_pct']:+.2f}%")
                    st.metric("Win rate", f"{oos_m['win_rate_pct']:.1f}%")
                    st.metric("Trade", oos_m["num_trades"])
                    st.metric("Max drawdown", f"{oos_m['max_drawdown_pct']:.2f}%")

                if oos_m["num_trades"] < 15:
                    st.warning(
                        f"Solo {oos_m['num_trades']} trade nella parte out-of-sample: campione piccolo, "
                        "risultato da prendere con cautela. Allunga 'Ore di storico' se possibile."
                    )
                elif oos_m["total_return_pct"] >= is_m["return_pct"] * 0.5 and oos_m["total_return_pct"] > 0:
                    st.success(
                        "Il risultato regge bene anche sui dati mai visti: è un segnale più solido, "
                        "non solo una taratura riuscita per caso sull'in-sample."
                    )
                elif oos_m["total_return_pct"] <= 0 < is_m["return_pct"]:
                    st.warning(
                        "L'in-sample era positivo ma l'out-of-sample no: probabile segnale di overfitting "
                        "— i parametri erano tarati sul rumore di quel periodo specifico, non su un vero pattern."
                    )

                oos_portfolio = wf["oos_portfolio"]
                if oos_portfolio.equity_curve:
                    eq_df = pd.DataFrame(oos_portfolio.equity_curve).set_index("timestamp")
                    st.markdown("**Curva equity out-of-sample**")
                    st.line_chart(eq_df["equity"], height=250)

                oos_candidate_counts = oos_m.get("candidate_counts", {})
                oos_chosen_counts = oos_m.get("chosen_counts", {})
                if oos_candidate_counts:
                    st.markdown("**Quanto ha pesato ciascuna crypto nella scelta (out-of-sample)**")
                    counts_df = pd.DataFrame({
                        "Crypto": list(oos_candidate_counts.keys()),
                        "Segnali validi": list(oos_candidate_counts.values()),
                        "Scelta": [oos_chosen_counts.get(p, 0) for p in oos_candidate_counts],
                    }).sort_values("Segnali validi", ascending=False)
                    st.dataframe(counts_df, use_container_width=True, hide_index=True)

                with st.expander("Griglia completa (tutte le combinazioni testate in-sample)"):
                    st.dataframe(wf["grid"], use_container_width=True, hide_index=True)

                if oos_portfolio.trade_log:
                    trades_df = pd.DataFrame(oos_portfolio.trade_log)
                    st.download_button("📥 Scarica trade log out-of-sample CSV", trades_df.to_csv(index=False),
                                        "walk_forward_oos_trades.csv", "text/csv")

# --------------------------------------------------------------- LIVE PAPER
with tab_live:
    st.subheader("Paper trading in tempo reale (dati live Coinbase, ordini solo simulati)")
    live_products = st.multiselect("Crypto da seguire live", PRODUCTS, default=PRODUCTS[:4], key="live_products")
    bar_seconds = st.select_slider("Durata barra (secondi) — più corta = reazione più rapida",
                                    options=[5, 10, 15, 30, 60], value=15, key="live_bar_seconds")

    with st.expander("🧬 Ricalibrazione automatica periodica"):
        st.caption(
            "Se attiva, ogni tot ore il sistema riesegue da solo la ricerca della soglia e "
            "dell'holding minimo migliori (stessa logica del walk-forward: taratura su una parte "
            "dello storico recente, verifica sull'altra) e aggiorna i parametri qui sopra e nel "
            "pannello laterale — ma solo se il campione di verifica è abbastanza grande da fidarsene, "
            "altrimenti lascia tutto com'è e lo segnala nel registro qui sotto."
        )
        recal_enabled = st.checkbox("Attiva ricalibrazione automatica", value=False, key="live_recal_enabled")
        recal_interval_h = st.slider("Ogni quante ore ricalibrare", 1, 48, 6, 1, key="live_recal_interval_h")

    if "live_feed" not in st.session_state:
        st.session_state.live_feed = None
    if "live_portfolio" not in st.session_state:
        st.session_state.live_portfolio = None
    if "live_trader" not in st.session_state:
        st.session_state.live_trader = None
    if "live_recal_last_at" not in st.session_state:
        st.session_state.live_recal_last_at = None
    if "live_recal_log" not in st.session_state:
        st.session_state.live_recal_log = []

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
                               take_profit_pct=take_profit_pct, min_hold_minutes=min_hold_minutes)
        st.session_state.live_feed = feed
        st.session_state.live_portfolio = portfolio
        st.session_state.live_trader = LivePaperTrader(feed, manager, portfolio)

    if stop_clicked and st.session_state.live_feed:
        st.session_state.live_feed.stop()

    if reset_clicked and st.session_state.live_portfolio:
        st.session_state.live_portfolio = Portfolio(
            starting_cash=starting_cash, fee_rate=fee_pct, max_position_pct=max_pos_pct,
            stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct,
            min_hold_minutes=min_hold_minutes)
        if st.session_state.live_trader:
            st.session_state.live_trader.portfolio = st.session_state.live_portfolio

    feed = st.session_state.live_feed
    trader = st.session_state.live_trader
    portfolio = st.session_state.live_portfolio

    if trader is not None:
        # Il pannello laterale (soglie, pesi, stop-loss...) può cambiare mentre la
        # simulazione live è già in corso: senza questo, il motore avviato con
        # "AVVIA" continuerebbe silenziosamente a usare le impostazioni di quel
        # momento, ignorando ogni modifica successiva agli slider.
        trader.manager = manager
        portfolio.min_hold_minutes = min_hold_minutes
        portfolio.stop_loss_pct = stop_loss_pct
        portfolio.take_profit_pct = take_profit_pct
        portfolio.fee_rate = fee_pct
        portfolio.max_position_pct = max_pos_pct

    if feed is None:
        st.info("Premi 'AVVIA SIMULAZIONE LIVE' per iniziare a ricevere dati reali da Coinbase e far lavorare il team di agenti (nessun ordine reale).")
    else:
        running = feed.is_running()
        status_icons = {"connesso": "🟢", "riconnessione...": "🟡", "errore": "🔴", "fermo": "⚪"}
        status_icon = status_icons.get(feed.status, "🟡" if running else "⚪")
        st.write(f"Stato feed: {status_icon} **{feed.status}**" + (f" — {feed.last_error}" if feed.last_error else ""))

        prices = trader.tick()

        if recal_enabled and live_products:
            last_at = st.session_state.live_recal_last_at
            due = last_at is None or (datetime.now(timezone.utc) - last_at).total_seconds() >= recal_interval_h * 3600
            if due:
                with st.spinner("Ricalibrazione automatica in corso (taratura + verifica su dati recenti)..."):
                    keep_screen_awake()
                    portfolio_kwargs_recal = dict(starting_cash=starting_cash, fee_rate=fee_pct,
                                                   max_position_pct=max_pos_pct, stop_loss_pct=stop_loss_pct,
                                                   take_profit_pct=take_profit_pct)
                    recal = recalibrate(live_products, granularity=3600, hours=24 * 45,
                                         weights=weights, portfolio_kwargs=portfolio_kwargs_recal)
                st.session_state.live_recal_last_at = datetime.now(timezone.utc)
                st.session_state.live_recal_log.insert(0, recal)
                if recal["applied"]:
                    st.session_state["cfg_buy_th"] = recal["best_threshold"]
                    st.session_state["cfg_sell_th"] = -recal["best_threshold"]
                    st.session_state["cfg_min_hold"] = int(recal["best_min_hold"])
                    for agent_name, w in (recal.get("best_weights") or {}).items():
                        st.session_state[f"cfg_weight_{agent_name}"] = w
                st.rerun()

        if st.session_state.live_recal_log:
            with st.expander(f"📋 Registro ricalibrazioni ({len(st.session_state.live_recal_log)})"):
                for entry in st.session_state.live_recal_log[:10]:
                    icon = "✅" if entry["applied"] else "⏸️"
                    st.write(f"{icon} **{entry['timestamp'].strftime('%Y-%m-%d %H:%M UTC')}** — {entry['reason']}")

        metrics = portfolio.metrics(prices)
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Equity", f"${metrics['equity']:,.2f}", f"{metrics['total_return_pct']:+.2f}%")
        m2.metric("Posizioni aperte", metrics["open_positions"])
        m3.metric("Trade chiusi", metrics["num_trades"])
        m4.metric("Win rate", f"{metrics['win_rate_pct']:.1f}%")
        m5.metric("Cash disponibile", f"${metrics['cash']:,.2f}")

        st.markdown("**🧠 Decisioni del team di agenti (ultimo tick)**")
        st.caption(
            "'Azione' è cosa vorrebbe fare l'agente in base al punteggio. 'Eseguito' dice se è "
            "davvero successo: un BUY/SELL può comparire come Azione ma restare bloccato (es. "
            "dall'holding minimo) senza che scatti nessun trade — non è un bug, è il vincolo di rischio."
        )
        rows = []
        for p, d in trader.last_decisions.items():
            azione = d["action"]
            eseguito = "✅" if d.get("executed") else ("⏳ bloccato" if d.get("blocked_by_min_hold") else "—")
            rows.append({
                "Crypto": p, "Prezzo": prices.get(p), "Azione": azione, "Eseguito": eseguito,
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

# ---------------------------------------------------------- POLYMARKET ARB
with tab_poly:
    st.subheader("Monitor di sola osservazione — arbitraggio su prediction market crypto (Polymarket)")
    st.caption(
        "Legge dati PUBBLICI reali da Polymarket (Gamma API + CLOB API): nessuna chiave privata, "
        "nessun ordine reale viene mai inviato, nessuna esecuzione automatica. Calcola lo scostamento "
        "di YES+NO dal fair value di 1.00$ sui mercati crypto attivi e segnala quando supera la soglia "
        "di ingresso, fino a quando rientra sotto la soglia di uscita. I numeri sono stime lorde "
        "sull'order book letto in quel momento, non garanzie su trade futuri."
    )

    pc1, pc2, pc3, pc4 = st.columns(4)
    with pc1:
        poly_entry = st.slider("Soglia ingresso (centesimi)", 0.5, 10.0, 2.0, 0.5, key="poly_entry") / 100
    with pc2:
        poly_exit = st.slider("Soglia uscita (centesimi)", 0.0, 5.0, 0.5, 0.5, key="poly_exit") / 100
    with pc3:
        poly_fee = st.slider("Commissione stimata per lato %", 0.0, 2.0, 0.0, 0.1, key="poly_fee") / 100
    with pc4:
        poly_interval = st.select_slider("Intervallo scansione (secondi)", [10, 15, 30, 60, 120], value=30, key="poly_interval")

    if poly_exit >= poly_entry:
        st.warning("La soglia di uscita deve essere minore di quella di ingresso, altrimenti l'opportunità si chiuderebbe subito.")

    if "poly_monitor" not in st.session_state:
        st.session_state.poly_monitor = None
    if "poly_running" not in st.session_state:
        st.session_state.poly_running = False
    if "poly_events" not in st.session_state:
        st.session_state.poly_events = []
    if "poly_last_scan_info" not in st.session_state:
        st.session_state.poly_last_scan_info = None

    pb1, pb2, pb3 = st.columns(3)
    with pb1:
        poly_start = st.button("🟢 AVVIA MONITORAGGIO", type="primary", use_container_width=True,
                                key="poly_start_btn", disabled=poly_exit >= poly_entry)
    with pb2:
        poly_stop = st.button("🔴 FERMA", use_container_width=True, key="poly_stop_btn")
    with pb3:
        poly_reset = st.button("♻️ AZZERA REGISTRO", use_container_width=True, key="poly_reset_btn")

    if poly_start:
        st.session_state.poly_monitor = ArbitrageMonitor(ArbitrageConfig(
            entry_threshold=poly_entry, exit_threshold=poly_exit, fee_rate=poly_fee,
        ))
        st.session_state.poly_running = True
    if poly_stop:
        st.session_state.poly_running = False
    if poly_reset:
        st.session_state.poly_events = []
        st.session_state.poly_last_scan_info = None

    if st.session_state.poly_monitor is not None:
        # Come per il live trading: le soglie possono cambiare mentre gira,
        # e devono applicarsi subito senza dover fermare e riavviare.
        st.session_state.poly_monitor.config.entry_threshold = poly_entry
        st.session_state.poly_monitor.config.exit_threshold = poly_exit
        st.session_state.poly_monitor.config.fee_rate = poly_fee

    if not st.session_state.poly_running:
        st.info("Premi 'AVVIA MONITORAGGIO' per iniziare a leggere i mercati crypto attivi su Polymarket (nessun ordine reale).")
    else:
        keep_screen_awake()
        monitor = st.session_state.poly_monitor
        snapshots = []
        try:
            with st.spinner("Scansione mercati Polymarket..."):
                markets = fetch_active_crypto_markets(limit=200)
                token_ids = []
                for m in markets:
                    token_ids.append(m["yes_token_id"])
                    token_ids.append(m["no_token_id"])
                books = fetch_books_batch(token_ids) if token_ids else {}
                for market in markets:
                    yes_quote = best_bid_ask(books.get(market["yes_token_id"]))
                    no_quote = best_bid_ask(books.get(market["no_token_id"]))
                    snap = monitor.snapshot(market, yes_quote, no_quote)
                    if snap is not None:
                        snapshots.append(snap)
                    for event in monitor.evaluate(market, yes_quote, no_quote):
                        st.session_state.poly_events.insert(0, event)
            st.session_state.poly_last_scan_info = {
                "at": datetime.now(timezone.utc), "n_markets": len(markets), "error": None,
            }
        except Exception as e:
            st.session_state.poly_last_scan_info = {
                "at": datetime.now(timezone.utc), "n_markets": 0,
                "error": f"{type(e).__name__}: {e}",
            }

        info = st.session_state.poly_last_scan_info
        if info and info["error"]:
            st.error(f"Errore durante la scansione: {info['error']} — riprovo al prossimo ciclo.")
        elif info:
            st.write(
                f"🟢 Ultima scansione: **{info['at'].strftime('%H:%M:%S UTC')}** — "
                f"{info['n_markets']} mercati crypto osservati, "
                f"{len(monitor.open_positions)} opportunità aperte"
            )

        p1, p2 = st.columns(2)
        p1.metric("Opportunità aperte ora", len(monitor.open_positions))
        p2.metric("Eventi registrati (totale)", len(st.session_state.poly_events))

        # Schede verticali invece di st.dataframe: su iPhone lo scroll orizzontale
        # di una tabella larga confonde il tocco con il ridimensionamento/riordino
        # delle colonne. Una scheda per riga elimina lo scroll laterale.
        if snapshots:
            st.markdown("**🔍 Migliori spread osservati ora (anche sotto soglia)**")
            st.caption(
                "Serve a capire se il monitor sta davvero lavorando anche quando non scatta nessuna "
                "opportunità: su Polymarket i grandi scostamenti vengono chiusi in pochi secondi da bot "
                "professionali, quindi vedere 0 opportunità aperte è normale, non un malfunzionamento."
            )
            top_snapshots = sorted(snapshots, key=lambda s: s["edge_per_share"], reverse=True)[:15]
            for s in top_snapshots:
                with st.container(border=True):
                    st.write(f"**{s['question']}**")
                    st.caption(
                        f"Edge {s['edge_per_share']*100:+.2f}c · YES ask {s['yes_ask']:.3f} · "
                        f"NO ask {s['no_ask']:.3f} · Size disp. {s['size_disponibile']:.0f}"
                    )

        if monitor.open_positions:
            st.markdown("**🔓 Opportunità attualmente aperte**")
            for o in monitor.open_positions.values():
                with st.container(border=True):
                    st.write(f"**{o.question}**")
                    st.caption(
                        f"Aperta alle {o.opened_at.strftime('%H:%M:%S UTC')} · "
                        f"Edge ingresso {o.entry_edge*100:+.2f}c · YES ask {o.yes_ask:.3f} · "
                        f"NO ask {o.no_ask:.3f} · Size disp. {o.available_size:.0f}"
                    )

        if st.session_state.poly_events:
            st.markdown("**📒 Registro eventi (apertura/chiusura)**")
            ev_df = pd.DataFrame(st.session_state.poly_events)
            st.download_button("📥 Scarica registro completo CSV", ev_df.to_csv(index=False),
                                "polymarket_opportunities.csv", "text/csv")
            for ev in st.session_state.poly_events[:20]:
                icona = "🟢" if ev["tipo"] == "APERTURA" else "🔴"
                ts = ev["timestamp"].strftime("%H:%M:%S UTC")
                with st.container(border=True):
                    st.write(f"{icona} **{ev['tipo']}** · {ts} · {ev['question']}")
                    if ev["tipo"] == "APERTURA":
                        st.caption(
                            f"Edge {ev['edge_per_share']*100:+.2f}c · YES ask {ev['yes_ask']:.3f} · "
                            f"NO ask {ev['no_ask']:.3f} · Size disp. {ev['size_disponibile']:.0f}"
                        )
                    else:
                        st.caption(
                            f"Ingresso {ev['edge_ingresso']*100:+.2f}c → uscita {ev['edge_uscita']*100:+.2f}c · "
                            f"durata {ev['durata_secondi']:.0f}s"
                        )
            if len(st.session_state.poly_events) > 20:
                st.caption(f"Mostrati gli ultimi 20 eventi su {len(st.session_state.poly_events)} totali — scarica il CSV per vederli tutti.")

        import time
        time.sleep(poly_interval)
        st.rerun()

st.divider()
st.caption(
    "⚠️ Questo strumento è puramente simulativo/educativo: nessun ordine reale viene inviato a Coinbase. "
    "Le performance passate (anche simulate) non garantiscono risultati futuri. Prima di considerare denaro "
    "reale servirebbero: validazione statistica su molti più dati, gestione del rischio più rigorosa e "
    "consapevolezza che la 'latenza a frazioni di secondo' è dominata da trading firms con infrastrutture "
    "dedicate — qui l'obiettivo realistico è reagire più in fretta usando l'order-flow, non batterle sulla latenza pura."
)
