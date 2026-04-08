"""
MARKET FILTER
==============
Deteksi kondisi market: trending/ranging/volatile
Skip sideways, prioritize volatile trending
"""

import numpy as np
import logging

logger = logging.getLogger("MARKET_FILTER")


class MarketFilter:
    def __init__(self):
        self.min_volume_threshold = 100  # USDT minimum (sangat rendah untuk small account)
        self.atr_period = 14
        self.adx_period = 14

    def analyze(self, candles: list) -> dict:
        """
        Analisis kondisi market.
        Returns dict dengan: skip, reason, condition, trending, volatility
        """
        result = {
            "skip": False,
            "reason": "",
            "condition": "unknown",
            "trending": False,
            "volatility": "medium",
            "adx": 0
        }

        try:
            if not candles or len(candles) < 20:
                result["skip"] = True
                result["reason"] = "insufficient data"
                return result

            closes = np.array([c[4] for c in candles])
            highs  = np.array([c[2] for c in candles])
            lows   = np.array([c[3] for c in candles])
            volumes = np.array([c[5] for c in candles])

            # ─── Volume Filter ────────────────────────────────────────
            avg_volume = np.mean(volumes[-20:])
            if avg_volume < self.min_volume_threshold:
                result["skip"] = True
                result["reason"] = f"low volume: {avg_volume:.0f}"
                return result

            # ─── ATR / Volatility ─────────────────────────────────────
            atr = self._atr(highs, lows, closes)
            atr_pct = (atr / closes[-1]) * 100

            if atr_pct < 0.05:  # Sangat flat
                result["skip"] = True
                result["reason"] = f"ultra low volatility: {atr_pct:.3f}%"
                return result

            if atr_pct > 5.0:  # Terlalu ekstrem
                result["volatility"] = "extreme"
                result["condition"] = "volatile"
                result["trending"] = False
                # Jangan skip - kita suka volatility, tapi hati-hati
            elif atr_pct > 1.0:
                result["volatility"] = "high"
            elif atr_pct > 0.3:
                result["volatility"] = "medium"
            else:
                result["volatility"] = "low"

            # ─── Trend Detection (ADX-like) ───────────────────────────
            adx_value = self._simple_adx(highs, lows, closes)
            result["adx"] = adx_value

            if adx_value > 25:
                result["trending"] = True
                result["condition"] = "trending"
            elif adx_value < 15:
                result["condition"] = "ranging"
                # Ranging market → kurangi frequency tapi jangan stop total
                # Kita masih bisa trade reversals

            # ─── Detect Sideways (choppy) ────────────────────────────
            if self._is_choppy(closes):
                result["condition"] = "choppy"
                # Lebih banyak false signal → skip untuk efisiensi
                if adx_value < 15:
                    result["skip"] = True
                    result["reason"] = "choppy sideways market"
                    return result

            if not result["condition"] or result["condition"] == "unknown":
                result["condition"] = "neutral"

        except Exception as e:
            logger.error(f"Market filter error: {e}")

        return result

    def _atr(self, highs, lows, closes, period=14):
        """Simple ATR"""
        trs = []
        for i in range(1, min(period+1, len(closes))):
            tr = max(
                highs[-i] - lows[-i],
                abs(highs[-i] - closes[-i-1]),
                abs(lows[-i] - closes[-i-1])
            )
            trs.append(tr)
        return sum(trs) / len(trs) if trs else 0

    def _simple_adx(self, highs, lows, closes, period=14) -> float:
        """Simplified ADX calculation"""
        if len(closes) < period + 1:
            return 25  # Default neutral

        dm_plus = []
        dm_minus = []
        tr_list = []

        for i in range(1, len(closes)):
            move_up = highs[i] - highs[i-1]
            move_down = lows[i-1] - lows[i]
            
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
            tr_list.append(tr)
            
            if move_up > move_down and move_up > 0:
                dm_plus.append(move_up)
            else:
                dm_plus.append(0)
            
            if move_down > move_up and move_down > 0:
                dm_minus.append(move_down)
            else:
                dm_minus.append(0)

        if len(tr_list) < period:
            return 25

        atr_sum = sum(tr_list[-period:])
        if atr_sum == 0:
            return 0
        
        di_plus = (sum(dm_plus[-period:]) / atr_sum) * 100
        di_minus = (sum(dm_minus[-period:]) / atr_sum) * 100
        
        di_sum = di_plus + di_minus
        if di_sum == 0:
            return 0

        dx = abs(di_plus - di_minus) / di_sum * 100
        return dx

    def _is_choppy(self, closes, lookback=15) -> bool:
        """
        Detect choppy/sideways: banyak direction changes
        """
        if len(closes) < lookback:
            return False

        recent = closes[-lookback:]
        direction_changes = 0
        
        for i in range(1, len(recent)-1):
            if (recent[i] > recent[i-1]) != (recent[i+1] > recent[i]):
                direction_changes += 1
        
        # Jika >60% candle adalah direction change → choppy
        return direction_changes / (lookback - 2) > 0.6
