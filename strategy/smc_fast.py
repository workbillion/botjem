"""
SMC FAST - Smart Money Concept (Speed Mode)
============================================
BOS, CHoCH, Order Block, FVG, Liquidity Sweep
Optimized untuk 1m/3m/5m scalping
"""

import numpy as np
from typing import Optional
import logging

logger = logging.getLogger("SMC_FAST")


class SMCFast:
    def __init__(self):
        self.swing_lookback = 5  # Lebih kecil = lebih cepat signal
        self.ob_lookback = 10
        self.fvg_min_gap_pct = 0.05  # 0.05% minimum FVG

    def analyze(self, candles_5m: list, candles_1m: list) -> dict:
        """
        Analisis SMC lengkap. Return signal dict.
        candles: list of [timestamp, open, high, low, close, volume]
        """
        result = {
            "bos": None,         # "BULLISH" / "BEARISH"
            "choch": None,       # "BULLISH" / "BEARISH"
            "order_block": None, # "BULL" / "BEAR"
            "fvg": None,         # "BULL" / "BEAR"
            "liquidity_sweep": None,  # "HIGH" / "LOW"
            "long_score": 0,
            "short_score": 0
        }

        try:
            if not candles_5m or len(candles_5m) < 20:
                return result

            closes = np.array([c[4] for c in candles_5m])
            highs  = np.array([c[2] for c in candles_5m])
            lows   = np.array([c[3] for c in candles_5m])
            opens  = np.array([c[1] for c in candles_5m])

            # ─── Swing High / Low ─────────────────────────────────────
            swing_highs, swing_lows = self._find_swings(highs, lows)

            # ─── BOS Detection ───────────────────────────────────────
            bos = self._detect_bos(closes, swing_highs, swing_lows)
            result["bos"] = bos
            if bos == "BULLISH":
                result["long_score"] += 25
            elif bos == "BEARISH":
                result["short_score"] += 25

            # ─── CHoCH Detection ─────────────────────────────────────
            choch = self._detect_choch(closes, highs, lows, swing_highs, swing_lows)
            result["choch"] = choch
            if choch == "BULLISH":
                result["long_score"] += 20
            elif choch == "BEARISH":
                result["short_score"] += 20

            # ─── Order Block ─────────────────────────────────────────
            ob = self._detect_order_block(opens, closes, highs, lows)
            result["order_block"] = ob
            if ob == "BULL":
                result["long_score"] += 20
            elif ob == "BEAR":
                result["short_score"] += 20

            # ─── FVG (Fair Value Gap) ────────────────────────────────
            fvg = self._detect_fvg(highs, lows)
            result["fvg"] = fvg
            if fvg == "BULL":
                result["long_score"] += 10
            elif fvg == "BEAR":
                result["short_score"] += 10

            # ─── Liquidity Sweep ─────────────────────────────────────
            liq_sweep = self._detect_liquidity_sweep(candles_1m, swing_highs, swing_lows, highs, lows)
            result["liquidity_sweep"] = liq_sweep
            if liq_sweep == "LOW":
                result["long_score"] += 20  # Swept low → expect bounce up
            elif liq_sweep == "HIGH":
                result["short_score"] += 20  # Swept high → expect drop

        except Exception as e:
            logger.error(f"SMC analyze error: {e}")

        return result

    def _find_swings(self, highs: np.ndarray, lows: np.ndarray) -> tuple:
        """Deteksi swing high/low"""
        n = len(highs)
        lb = self.swing_lookback
        swing_highs = []
        swing_lows = []

        for i in range(lb, n - lb):
            if highs[i] == max(highs[i-lb:i+lb+1]):
                swing_highs.append((i, highs[i]))
            if lows[i] == min(lows[i-lb:i+lb+1]):
                swing_lows.append((i, lows[i]))

        return swing_highs, swing_lows

    def _detect_bos(self, closes: np.ndarray, swing_highs: list, swing_lows: list) -> Optional[str]:
        """
        Break of Structure:
        - Bullish BOS: close breaks above last swing high
        - Bearish BOS: close breaks below last swing low
        """
        current_close = closes[-1]
        prev_close = closes[-2]

        if swing_highs:
            last_sh = swing_highs[-1][1]
            if prev_close < last_sh and current_close > last_sh:
                return "BULLISH"

        if swing_lows:
            last_sl = swing_lows[-1][1]
            if prev_close > last_sl and current_close < last_sl:
                return "BEARISH"

        return None

    def _detect_choch(self, closes, highs, lows, swing_highs, swing_lows) -> Optional[str]:
        """
        Change of Character:
        - Bullish CHoCH: setelah downtrend, break swing high baru
        - Bearish CHoCH: setelah uptrend, break swing low baru
        """
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return None

        # Bearish trend (HH structure)
        # CHoCH Bullish: lower high tapi kemudian break up
        recent_lows = [sl[1] for sl in swing_lows[-3:]]
        recent_highs = [sh[1] for sh in swing_highs[-3:]]

        # Deteksi reversal sederhana
        if len(recent_lows) >= 2 and recent_lows[-1] < recent_lows[-2]:
            # Lower low → bearish trend
            if closes[-1] > recent_highs[-1] if recent_highs else False:
                return "BULLISH"

        if len(recent_highs) >= 2 and recent_highs[-1] < recent_highs[-2]:
            # Lower high → bearish
            if closes[-1] < recent_lows[-1] if recent_lows else False:
                return "BEARISH"

        return None

    def _detect_order_block(self, opens, closes, highs, lows) -> Optional[str]:
        """
        Order Block: Candle terakhir sebelum impulse move
        - Bullish OB: bearish candle sebelum strong bullish impulse
        - Bearish OB: bullish candle sebelum strong bearish impulse
        """
        if len(closes) < 5:
            return None

        current_price = closes[-1]

        # Look back 5-15 candle untuk find OB
        for i in range(2, min(15, len(closes)-1)):
            idx = -(i+1)
            
            candle_body = abs(closes[idx] - opens[idx])
            candle_range = highs[idx] - lows[idx]
            if candle_range == 0:
                continue
            
            body_ratio = candle_body / candle_range

            # Strong impulse candle setelah OB
            next_body = abs(closes[idx+1] - opens[idx+1])
            impulse_ratio = next_body / candle_range if candle_range > 0 else 0

            if impulse_ratio > 0.7:  # Strong impulse
                # Bearish OB (bullish candle before drop)
                if closes[idx] > opens[idx] and closes[idx+1] < opens[idx+1]:
                    ob_top = highs[idx]
                    ob_bottom = lows[idx]
                    # Price returning to OB zone
                    if ob_bottom <= current_price <= ob_top:
                        return "BEAR"

                # Bullish OB (bearish candle before rise)
                if closes[idx] < opens[idx] and closes[idx+1] > opens[idx+1]:
                    ob_top = highs[idx]
                    ob_bottom = lows[idx]
                    if ob_bottom <= current_price <= ob_top:
                        return "BULL"

        return None

    def _detect_fvg(self, highs: np.ndarray, lows: np.ndarray) -> Optional[str]:
        """
        Fair Value Gap:
        - Bullish FVG: low[i+1] > high[i-1] (gap up)
        - Bearish FVG: high[i+1] < low[i-1] (gap down)
        Price currently inside gap = strong signal
        """
        if len(highs) < 5:
            return None

        current_price = (highs[-1] + lows[-1]) / 2

        # Check recent candles untuk FVG
        for i in range(2, min(10, len(highs)-1)):
            # Bullish FVG
            if lows[-i] > highs[-(i+2)]:
                gap_top = lows[-i]
                gap_bottom = highs[-(i+2)]
                if gap_bottom <= current_price <= gap_top:
                    return "BULL"

            # Bearish FVG
            if highs[-i] < lows[-(i+2)]:
                gap_top = lows[-(i+2)]
                gap_bottom = highs[-i]
                if gap_bottom <= current_price <= gap_top:
                    return "BEAR"

        return None

    def _detect_liquidity_sweep(self, candles_1m, swing_highs, swing_lows, highs_5m, lows_5m) -> Optional[str]:
        """
        Liquidity Sweep: Price briefly breaks key level lalu balik
        - Swept high → expect reversal down
        - Swept low → expect reversal up
        """
        if not candles_1m or len(candles_1m) < 5:
            return None

        # Recent 1m candles
        recent_1m_highs = [c[2] for c in candles_1m[-5:]]
        recent_1m_lows  = [c[3] for c in candles_1m[-5:]]
        recent_1m_closes = [c[4] for c in candles_1m[-5:]]

        current_close = recent_1m_closes[-1]

        # Key levels dari 5m swing
        if swing_highs:
            key_high = swing_highs[-1][1]
            # Spike above key high tapi close below
            if max(recent_1m_highs) > key_high and current_close < key_high:
                return "HIGH"

        if swing_lows:
            key_low = swing_lows[-1][1]
            # Spike below key low tapi close above
            if min(recent_1m_lows) < key_low and current_close > key_low:
                return "LOW"

        return None
