"""
AGGRESSIVE RISK MANAGER
========================
Dynamic position sizing, SL/TP calculation
Risk: 2%-5% per trade | Leverage: 10x-20x
"""

import logging
import math

logger = logging.getLogger("RISK_MGR")

# Symbol precisions
SYMBOL_PRECISION = {
    "BTCUSDT": {"qty": 3, "price": 1},
    "ETHUSDT": {"qty": 2, "price": 2},
    "SOLUSDT": {"qty": 1, "price": 3},
    "BNBUSDT": {"qty": 2, "price": 2},
    "XRPUSDT": {"qty": 0, "price": 4},
    "DOGEUSDT": {"qty": 0, "price": 5},
    "ADAUSDT": {"qty": 0, "price": 4},
    "AVAXUSDT": {"qty": 1, "price": 3},
    "DEFAULT": {"qty": 2, "price": 4},
}


class AggressiveRiskManager:
    def __init__(self, config: dict):
        self.config = config
        self.risk_cfg = config["risk"]
        self.balance = 0
        self.drawdown_level = 0  # 0=normal, 1=caution, 2=reduce

    def set_balance(self, balance: float):
        self.balance = balance

    def calculate_position(self, balance: float, price: float, direction: str,
                           candles: list, confluence_score: float) -> dict:
        """
        Hitung position size, SL, TP berdasarkan:
        - Balance saat ini
        - ATR (volatility-based SL)
        - Confluence score (lebih tinggi → risk lebih besar)
        - Drawdown level
        """
        self.balance = balance

        # ─── Dynamic Risk % ───────────────────────────────────────────
        risk_pct = self._get_dynamic_risk(confluence_score)

        # ─── ATR-based SL Distance ────────────────────────────────────
        atr = self._calculate_atr(candles)
        if atr == 0:
            atr = price * 0.003  # Default 0.3% jika tidak bisa hitung

        sl_multiplier = self.risk_cfg.get("sl_atr_mult", 1.5)
        sl_distance = atr * sl_multiplier

        # Minimum SL distance (prevent too tight)
        min_sl_pct = self.risk_cfg.get("min_sl_pct", 0.002)
        sl_distance = max(sl_distance, price * min_sl_pct)

        # ─── SL / TP Prices ───────────────────────────────────────────
        if direction == "LONG":
            sl_price = price - sl_distance
            tp1_price = price + (sl_distance * self.risk_cfg.get("tp1_rr", 1.0))
            tp2_price = price + (sl_distance * self.risk_cfg.get("tp2_rr", 1.8))
        else:
            sl_price = price + sl_distance
            tp1_price = price - (sl_distance * self.risk_cfg.get("tp1_rr", 1.0))
            tp2_price = price - (sl_distance * self.risk_cfg.get("tp2_rr", 1.8))

        # ─── Position Size ────────────────────────────────────────────
        risk_amount = balance * (risk_pct / 100)
        leverage = self.config["trading"]["leverage"]

        # Notional size berdasarkan risk
        # risk_amount = (sl_distance / price) * notional_size
        # notional_size = risk_amount * price / sl_distance
        notional_size = risk_amount * leverage
        
        # Validasi notional tidak melebihi margin tersedia
        max_notional = balance * leverage * 0.8  # Max 80% margin
        notional_size = min(notional_size, max_notional)

        quantity = notional_size / price

        # Round to exchange precision
        prec = self._get_precision(candles)
        qty_prec = SYMBOL_PRECISION.get("DEFAULT")["qty"]
        quantity = math.floor(quantity * 10**qty_prec) / 10**qty_prec

        # Minimum quantity check
        min_qty = self.risk_cfg.get("min_quantity", 0.001)
        if quantity < min_qty:
            logger.warning(f"Quantity {quantity} terlalu kecil (min: {min_qty})")
            return {"valid": False, "reason": f"Quantity too small: {quantity}"}

        # Trailing distance = 50% dari TP1 distance
        trailing_distance = abs(tp1_price - price) * 0.5

        logger.debug(f"Risk calc: balance={balance:.2f} risk={risk_pct:.1f}% "
                    f"sl_dist={sl_distance:.4f} qty={quantity} notional={notional_size:.2f}")

        return {
            "valid": True,
            "quantity": quantity,
            "sl_price": round(sl_price, 4),
            "tp1_price": round(tp1_price, 4),
            "tp2_price": round(tp2_price, 4),
            "risk_amount": risk_amount,
            "risk_pct": risk_pct,
            "notional_size": notional_size,
            "trailing_distance": trailing_distance,
            "atr": atr,
            "sl_distance": sl_distance
        }

    def _get_dynamic_risk(self, confluence_score: float) -> float:
        """
        Dynamic risk berdasarkan confluence dan drawdown:
        - Confluence tinggi → risk lebih besar
        - Drawdown tinggi → risk lebih kecil
        """
        base_min = self.risk_cfg["risk_per_trade_min_pct"]  # 2%
        base_max = self.risk_cfg["risk_per_trade_max_pct"]  # 5%

        # Scale risk dengan confidence (65%-100% → 2%-5%)
        min_conf = self.config["trading"]["min_confidence"]  # 65
        conf_ratio = max(0, (confluence_score - min_conf) / (100 - min_conf))
        risk_pct = base_min + (conf_ratio * (base_max - base_min))

        # Reduce jika dalam drawdown
        if self.drawdown_level == 1:
            risk_pct *= 0.7  # -30%
        elif self.drawdown_level >= 2:
            risk_pct *= 0.5  # -50%

        return min(risk_pct, base_max)

    def _calculate_atr(self, candles: list, period: int = 14) -> float:
        """Calculate Average True Range"""
        if not candles or len(candles) < period + 1:
            return 0

        true_ranges = []
        for i in range(1, min(period + 1, len(candles))):
            high = candles[-i][2]
            low = candles[-i][3]
            prev_close = candles[-i-1][4]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)

        return sum(true_ranges) / len(true_ranges) if true_ranges else 0

    def update_drawdown(self, current_balance: float):
        """Update drawdown level berdasarkan penurunan dari start"""
        if self.balance == 0:
            return

        drawdown_pct = ((self.balance - current_balance) / self.balance) * 100

        if drawdown_pct < 3:
            self.drawdown_level = 0
        elif drawdown_pct < 6:
            self.drawdown_level = 1
            logger.info(f"⚠️  Drawdown {drawdown_pct:.1f}% → Reducing risk")
        else:
            self.drawdown_level = 2
            logger.warning(f"🚨 Drawdown {drawdown_pct:.1f}% → Minimum risk mode")

    def _get_precision(self, candles: list) -> int:
        return 4
