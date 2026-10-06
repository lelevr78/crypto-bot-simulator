"""Ricalibrazione automatica periodica per il paper trading live: rifà da sola
la ricerca soglia/holding migliore (stessa logica del walk-forward: taratura
su una parte dello storico recente, verifica sull'altra) e restituisce se e
come applicare il risultato — mai a scatola chiusa, sempre con un motivo
leggibile registrato per l'utente."""
from __future__ import annotations

from datetime import datetime, timezone

from .batch_backtest import fetch_multi_candles
from .manager import WEIGHT_PROFILES
from .multi_asset_backtest import run_walk_forward

DEFAULT_THRESHOLDS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35]
DEFAULT_MIN_HOLDS = [60, 240, 480, 720]
MIN_OOS_TRADES = 10  # sotto questa soglia il campione è troppo piccolo per fidarsi


def recalibrate(products: list[str], granularity: int, hours: int,
                 weights: dict | None, portfolio_kwargs: dict | None,
                 split_ratio: float = 0.6) -> dict:
    """Scarica storico recente, cerca soglia+holding+profilo di pesi migliori
    SOLO sulla prima parte, verifica sulla seconda (mai usata in taratura), e
    decide se il risultato è abbastanza solido da poter essere applicato in
    automatico."""
    now = datetime.now(timezone.utc)
    result = {
        "timestamp": now, "applied": False, "best_threshold": None, "best_min_hold": None,
        "best_weights": None, "best_weight_profile": None,
        "is_return_pct": None, "oos_return_pct": None, "oos_trades": None, "reason": "",
    }
    try:
        candles_by_product = fetch_multi_candles(products, granularity, hours)
        wf = run_walk_forward(
            candles_by_product, DEFAULT_THRESHOLDS, DEFAULT_MIN_HOLDS,
            weights=weights, weight_profiles=WEIGHT_PROFILES,
            portfolio_kwargs=portfolio_kwargs, split_ratio=split_ratio,
        )
    except Exception as e:
        result["reason"] = f"ricalibrazione fallita: {type(e).__name__}: {e}"
        return result

    is_m, oos_m = wf["is_metrics"], wf["oos_metrics"]
    result.update({
        "best_threshold": wf["best_threshold"], "best_min_hold": wf["best_min_hold"],
        "best_weights": wf["best_weights"], "best_weight_profile": wf["best_weight_profile"],
        "is_return_pct": is_m["return_pct"], "oos_return_pct": oos_m["total_return_pct"],
        "oos_trades": oos_m["num_trades"],
    })

    if oos_m["num_trades"] < MIN_OOS_TRADES:
        result["reason"] = (
            f"campione out-of-sample troppo piccolo ({oos_m['num_trades']} trade): "
            "parametri NON applicati, restano quelli precedenti."
        )
        return result

    result["applied"] = True
    result["reason"] = (
        f"applicata soglia {wf['best_threshold']:.2f} / holding {int(wf['best_min_hold'])} min "
        f"/ pesi \"{wf['best_weight_profile']}\" "
        f"— in-sample {is_m['return_pct']:+.2f}%, out-of-sample {oos_m['total_return_pct']:+.2f}% "
        f"su {oos_m['num_trades']} trade."
    )
    return result
