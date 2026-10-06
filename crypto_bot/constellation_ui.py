"""Markup HTML/CSS per il pannello visivo "costellazione di agenti" nel paper
trading live: un nodo centrale con la decisione combinata del team, e
un'orbita pulsante per ciascun agente (colore verde/rosso e intensita' del
bagliore in base al segnale, spento/grigio se l'agente non ha dati in quel
momento). Solo markup statico via st.markdown(unsafe_allow_html=True),
nessuna dipendenza esterna, nessuna vera animazione dei dati — e' una
rappresentazione visiva dello stato calcolato, non un elemento interattivo."""
from __future__ import annotations

import math

AGENT_ANGLES = {"Momentum": -90, "MeanReversion": 0, "Breakout": 90, "OrderFlow": 180}
AGENT_SHORT = {"Momentum": "MOM", "MeanReversion": "MR", "Breakout": "BRK", "OrderFlow": "OF"}

CONSTELLATION_CSS = """
<style>
.cbs-constellation { position: relative; width: 220px; height: 220px; margin: 8px auto; }
.cbs-orb {
    position: absolute; width: 42px; height: 42px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    color: #fff; font-size: 0.62rem; font-weight: 700;
    animation-name: cbs-pulse; animation-iteration-count: infinite; animation-timing-function: ease-in-out;
}
.cbs-orb-label {
    position: absolute; transform: translate(-50%, -50%); text-align: center;
    font-size: 0.6rem; color: #fff; line-height: 1.3; white-space: nowrap;
    background: rgba(15, 23, 42, 0.78); padding: 1px 6px; border-radius: 6px;
}
.cbs-core {
    position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
    width: 82px; height: 82px; border-radius: 50%;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    color: #fff; text-align: center; z-index: 3;
}
.cbs-core-title { font-size: 0.62rem; opacity: 0.85; }
.cbs-core-action { font-size: 0.7rem; font-weight: 800; margin-top: 1px; }
.cbs-core-score { font-size: 0.6rem; opacity: 0.8; }
@keyframes cbs-pulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.16); }
}
</style>
"""


def _score_hue_lightness(score: float, available: bool) -> tuple[int, float]:
    if not available:
        return 217, 38.0  # blu spento: agente senza dati in questo momento (es. OrderFlow nel backtest)
    hue = 142 if score >= 0 else 0  # verde se punta al rialzo, rosso se al ribasso
    lightness = 32.0 + min(abs(score), 1.0) * 18.0
    return hue, lightness


def render_agent_constellation(product: str, action: str, combined_score: float,
                                confidence: float, signals: list, executed_icon: str) -> str:
    """signals: lista di Signal (agent, score, reason, available) del team per questo prodotto.
    Ritorna solo il markup del widget: CONSTELLATION_CSS va iniettato una volta sola a parte."""
    core_hue = {"BUY": 142, "SELL": 0, "HOLD": 217}.get(action, 217)
    core_lightness = 28.0 + min(max(confidence, 0.0), 1.0) * 20.0
    core_glow = 8 + min(max(confidence, 0.0), 1.0) * 22

    radius = 66
    label_radius = 96  # più lontano del centro degli orb: evita che l'etichetta finisca dietro il nodo centrale
    orbs = []
    for sig in signals:
        angle = AGENT_ANGLES.get(sig.agent, 0)
        rad = math.radians(angle)
        x, y = radius * math.cos(rad), radius * math.sin(rad)
        lx, ly = label_radius * math.cos(rad), label_radius * math.sin(rad)
        hue, lightness = _score_hue_lightness(sig.score, sig.available)
        intensity = min(abs(sig.score), 1.0) if sig.available else 0.0
        glow = 4 + intensity * 14
        pulse_dur = 3.4 - intensity * 2.0 if sig.available else 4.5
        opacity = 1.0 if sig.available else 0.4
        orb_style = (
            f"left:calc(50% + {x:.0f}px - 21px); top:calc(50% + {y:.0f}px - 21px); "
            f"background:hsl({hue} 70% {lightness:.0f}%); opacity:{opacity}; "
            f"box-shadow:0 0 {glow:.0f}px hsla({hue}, 80%, 55%, 0.9); "
            f"animation-duration:{pulse_dur:.1f}s;"
        )
        label_style = f"left:calc(50% + {lx:.0f}px); top:calc(50% + {ly:.0f}px);"
        agent_short = AGENT_SHORT.get(sig.agent, sig.agent[:3].upper())
        # Nessun ritorno a capo/indentazione nell'HTML: st.markdown interpreta righe
        # indentate con 4+ spazi come blocco di codice Markdown, non come HTML.
        # Etichetta solo col punteggio (breve, non rischia di uscire dai bordi):
        # l'agente è già identificato dalla sigla dentro l'orbita stessa.
        orbs.append(
            f'<div class="cbs-orb" style="{orb_style}">{agent_short}</div>'
            f'<div class="cbs-orb-label" style="{label_style}">{sig.score:+.2f}</div>'
        )

    action_label = {"BUY": "COMPRA", "SELL": "VENDI", "HOLD": "ATTENDE"}.get(action, action)
    core_style = (
        f"background:hsl({core_hue} 55% {core_lightness:.0f}%); "
        f"box-shadow:0 0 {core_glow:.0f}px hsla({core_hue}, 80%, 55%, 0.85);"
    )
    return (
        '<div class="cbs-constellation">'
        + "".join(orbs)
        + f'<div class="cbs-core" style="{core_style}">'
        + f'<div class="cbs-core-title">{product.replace("-USD", "")}</div>'
        + f'<div class="cbs-core-action">{executed_icon} {action_label}</div>'
        + f'<div class="cbs-core-score">{combined_score:+.2f}</div>'
        + "</div></div>"
    )
