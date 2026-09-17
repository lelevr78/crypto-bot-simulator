import streamlit as st
import pandas as pd
import numpy as np
import json
import time
import threading
from collections import defaultdict, deque
from datetime import datetime, timezone

st.set_page_config(page_title="Crypto Bot V20", layout="wide")

WS_URL = "wss://advanced-trade-ws.coinbase.com"
PRODUCTS = ["BTC-USD","ETH-USD","SOL-USD","XRP-USD","DOGE-USD","LINK-USD","ADA-USD","AVAX-USD"]

if "events" not in st.session_state:
    st.session_state.events = deque(maxlen=20000)
if "books" not in st.session_state:
    st.session_state.books = defaultdict(lambda: {
        "bids": {}, "asks": {}, "last_price": np.nan,
        "buy_volume": 0.0, "sell_volume": 0.0, "trade_count": 0
    })
if "stop" not in st.session_state:
    st.session_state.stop = threading.Event()
if "thread" not in st.session_state:
    st.session_state.thread = None

def add_event(x):
    st.session_state.events.append(x)

def f(x):
    try: return float(x)
    except: return np.nan

def process_trade(msg):
    for ev in msg.get("events", []):
        for t in ev.get("trades", []):
            p = t.get("product_id")
            price, size = f(t.get("price")), f(t.get("size"))
            side = str(t.get("side","")).upper()
            if not p or not np.isfinite(price) or not np.isfinite(size): continue
            b = st.session_state.books[p]
            b["last_price"] = price
            b["trade_count"] += 1
            if side == "BUY": b["buy_volume"] += size
            elif side == "SELL": b["sell_volume"] += size
            add_event({
                "timestamp": t.get("time", datetime.now(timezone.utc).isoformat()),
                "product": p, "type": "TRADE", "side": side,
                "price": price, "size": size
            })

def process_l2(msg):
    for ev in msg.get("events", []):
        for u in ev.get("updates", []):
            p = u.get("product_id")
            side = str(u.get("side","")).upper()
            price, qty = f(u.get("price_level")), f(u.get("new_quantity"))
            if not p or not np.isfinite(price) or not np.isfinite(qty): continue
            b = st.session_state.books[p]
            book = b["bids"] if side == "BID" else b["asks"]
            if qty <= 0: book.pop(price, None)
            else: book[price] = qty
            add_event({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "product": p, "type": "BOOK", "side": side,
                "price": price, "size": qty
            })

def worker(products, stop):
    try:
        import websocket
    except ImportError:
        add_event({"timestamp": datetime.now(timezone.utc).isoformat(),
                   "type":"ERROR","message":"Installa websocket-client."})
        return

    while not stop.is_set():
        ws = None
        try:
            ws = websocket.create_connection(WS_URL, timeout=10)
            ws.send(json.dumps({"type":"subscribe","channel":"market_trades","product_ids":products}))
            ws.send(json.dumps({"type":"subscribe","channel":"level2","product_ids":products}))
            add_event({"timestamp":datetime.now(timezone.utc).isoformat(),
                       "type":"STATUS","message":"WebSocket connesso"})
            ws.settimeout(2)
            while not stop.is_set():
                try:
                    msg = json.loads(ws.recv())
                    ch = msg.get("channel")
                    if ch == "market_trades": process_trade(msg)
                    elif ch == "l2_data": process_l2(msg)
                except Exception as e:
                    if "timed out" in str(e).lower(): continue
                    raise
        except Exception as e:
            add_event({"timestamp":datetime.now(timezone.utc).isoformat(),
                       "type":"ERROR","message":f"{type(e).__name__}: {e}"})
            time.sleep(3)
        finally:
            try:
                if ws: ws.close()
            except: pass

def start(products):
    if st.session_state.thread and st.session_state.thread.is_alive(): return
    st.session_state.stop.clear()
    st.session_state.thread = threading.Thread(
        target=worker, args=(products, st.session_state.stop), daemon=True)
    st.session_state.thread.start()

def stop():
    st.session_state.stop.set()

def summary(products):
    rows=[]
    for p in products:
        b=st.session_state.books[p]
        bids=sorted(b["bids"].items(), reverse=True)[:10]
        asks=sorted(b["asks"].items())[:10]
        bd=sum(q for _,q in bids); ad=sum(q for _,q in asks)
        imb=(bd-ad)/(bd+ad) if bd+ad else np.nan
        bb=bids[0][0] if bids else np.nan
        ba=asks[0][0] if asks else np.nan
        spr=(ba-bb)/((ba+bb)/2)*100 if np.isfinite(bb) and np.isfinite(ba) else np.nan
        tv=b["buy_volume"]+b["sell_volume"]
        rows.append({
            "Crypto":p, "Prezzo":b["last_price"], "Trade":b["trade_count"],
            "Buy vol":b["buy_volume"], "Sell vol":b["sell_volume"],
            "Buy %":b["buy_volume"]/tv*100 if tv else np.nan,
            "Bid":bb, "Ask":ba, "Spread %":spr,
            "Book imbalance":imb, "Bid depth":bd, "Ask depth":ad
        })
    return pd.DataFrame(rows)

st.title("🤖 Crypto Trading Bot V20")
st.success("V20 — FASE 1: REAL-TIME DATA + ORDER FLOW")
st.caption("Paper-only: nessun ordine reale. Prima raccogliamo dati e verifichiamo il potere predittivo dell'order flow.")

products=st.sidebar.multiselect("Crypto da monitorare", PRODUCTS, default=PRODUCTS[:5])

c1,c2=st.columns(2)
with c1:
    if st.button("🟢 AVVIA RACCOLTA DATI", type="primary", use_container_width=True):
        start(products)
with c2:
    if st.button("🔴 FERMA RACCOLTA", use_container_width=True):
        stop()

running=st.session_state.thread is not None and st.session_state.thread.is_alive() and not st.session_state.stop.is_set()
st.write("Stato:", "🟢 RACCOLTA ATTIVA" if running else "⚪ FERMO")

df=summary(products)
st.subheader("📊 Order Flow live")
st.dataframe(df, use_container_width=True, hide_index=True)

if not df.empty:
    chart=df.set_index("Crypto")[["Buy %"]].copy()
    chart["Sell %"]=100-chart["Buy %"]
    st.bar_chart(chart)

st.caption("Buy % = quota del volume dei trade classificati BUY. Book imbalance = (BID depth − ASK depth) / totale, sui primi 10 livelli.")

with st.session_state.stop:
    pass

st.subheader("🧪 Eventi grezzi")
events=list(st.session_state.events)
if events:
    edf=pd.DataFrame(events)
    st.write(f"Eventi in memoria: **{len(edf)}**")
    st.dataframe(edf.tail(200), use_container_width=True, hide_index=True)
    st.download_button("📥 Scarica CSV eventi V20", edf.to_csv(index=False),
                       "crypto_bot_v20_order_flow.csv", "text/csv")
else:
    st.info("Nessun evento ancora raccolto.")

st.subheader("🎯 Prossimo test")
st.markdown("Misureremo cosa succede a 10/30/60 secondi dopo ogni configurazione di buy pressure, book imbalance, accelerazione prezzo e volume. Solo dopo costruiremo il Pressure Score V20.")

if running:
    time.sleep(2)
    st.rerun()
