"""
SCALPING ENGINE
================
EMA 9/21, RSI, Volume Spike, Momentum Impulse
Fast signals untuk 1m/3m timeframe
"""

import numpy as np
from typing import Optional
import logging

logger = logging.getLogger("SCALPING")


def ema(values: np.ndarray, period: int) -> np.ndarray:
    """Exponential Moving Average"""
    k = 2 / (period + 1)
    result = np.zeros(len(values))
    result[0] = values[0]
    for i in range(1, len(values)):
        result[i] = values[i] * k + result[i-1] * (1 - k)
    return result


def rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    """RSI Indicator"""
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.zeros(len(closes))
    avg_loss = np.zeros(len(closes))
    
    if len(gains) < period:
        return np.full(len(closes), 50.0)
    
    avg_gain[period] = np.mean(gains[:period])
    avg_loss[period] = np.mean(losses[:period])
    
    for i in range(period + 1, len(closes)):
        avg_gain[i] = (avg_gain[i-1] * (period - 1) + gains[i-1]) / period
        avg_loss[i] = (avg_loss[i-1] * (period - 1) + losses[i-1]) / period
    
    rs = np.where(avg_loss != 0, avg_gain / avg_loss, 100)
    rsi_values = 100 - (100 / (1 + rs))
    return rsi_values


class ScalpingEngine:
    def __init__(self):
        self.ema_fast = 9
        self.ema_slow = 21
        self.rsi_period = 14
        self.rsi_oversold = 35    # Lebih longgar untuk agresif
        self.rsi_overbought = 65  # Lebih longgar untuk agresif
        self.volume_spike_mult = 1.5  # Volume spike jika > 1.5x avg

    def analyze(self, candles_1m: list, candles_3m: list) -> dict:
        """
        Analisis scalping indicators.
        Return signal dict.
        """
        result = {
            "ema_cross": None,      # "BULLISH" / "BEARISH"
            "rsi_signal": None,     # "OVERSOLD" / "OVERBOUGHT"
            "volume_spike": False,
            "momentum_impulse": False,
            "long_score": 0,
            "short_score": 0
        }

        try:
            if not candles_1m or len(candles_1m) < 30:
                return result

            closes_1m = np.array([c[4] for c in candles_1m])
            volumes_1m = np.array([c[5] for c in candles_1m])
            opens_1m   = np.array([c[1] for c in candles_1m])
            highs_1m   = np.array([c[2] for c in candles_1m])
            lows_1m    = np.array([c[3] for c in candles_1m])

            # ─── EMA Cross ───────────────────────────────────────────
            ema_fast_arr = ema(closes_1m, self.ema_fast)
            ema_slow_arr = ema(closes_1m, self.ema_slow)

            curr_fast = ema_fast_arr[-1]
            curr_slow = ema_slow_arr[-1]
            prev_fast = ema_fast_arr[-2]
            prev_slow = ema_slow_arr[-2]

            # Golden cross (fast crosses above slow)
            if prev_fast <= prev_slow and curr_fast > curr_slow:
                result["ema_cross"] = "BULLISH"
                result["long_score"] += 15
            # Death cross
            elif prev_fast >= prev_slow and curr_fast < curr_slow:
                result["ema_cross"] = "BEARISH"
                result["short_score"] += 15
            # Trend continuation
            elif curr_fast > curr_slow:
                result["long_score"] += 7
            elif curr_fast < curr_slow:
                result["short_score"] += 7

            # ─── RSI ─────────────────────────────────────────────────
            rsi_arr = rsi(closes_1m, self.rsi_period)
            current_rsi = rsi_arr[-1]
            prev_rsi = rsi_arr[-2]

            if current_rsi < self.rsi_oversold:
                result["rsi_signal"] = "OVERSOLD"
                result["long_score"] += 15
                # Extra jika baru keluar zona
                if prev_rsi <= current_rsi and current_rsi > self.rsi_oversold - 5:
                    result["long_score"] += 5
            elif current_rsi > self.rsi_overbought:
                result["rsi_signal"] = "OVERBOUGHT"
                result["short_score"] += 15
                if prev_rsi >= current_rsi and current_rsi < self.rsi_overbought + 5:
                    result["short_score"] += 5

            # ─── Volume Spike ────────────────────────────────────────
            avg_volume = np.mean(volumes_1m[-20:-1])
            current_volume = volumes_1m[-1]
            
            if avg_volume > 0 and current_volume > avg_volume * self.volume_spike_mult:
                result["volume_spike"] = True
                # Direction dari candle terakhir
                if closes_1m[-1] > opens_1m[-1]:
                    result["long_score"] += 15
                else:
                    result["short_score"] += 15

            # ─── Momentum Impulse (Sniper Mode) ──────────────────────
            impulse = self._detect_impulse(opens_1m, closes_1m, highs_1m, lows_1m, volumes_1m)
            result["momentum_impulse"] = impulse is not None
            
            if impulse == "BULLISH":
                result["long_score"] += 20
            elif impulse == "BEARISH":
                result["short_score"] += 20

            # ─── 3m trend confirmation ───────────────────────────────
            if candles_3m and len(candles_3m) >= 21:
                closes_3m = np.array([c[4] for c in candles_3m])
                ema9_3m = ema(closes_3m, 9)
                ema21_3m = ema(closes_3m, 21)
                
                if ema9_3m[-1] > ema21_3m[-1]:
                    result["long_score"] += 8
                else:
                    result["short_score"] += 8

        except Exception as e:
            logger.error(f"Scalping analyze error: {e}")

        return result

    def _detect_impulse(self, opens, closes, highs, lows, volumes) -> Optional[str]:
        """
        Deteksi candle impulsif kuat (pump/dump sudden move)
        Kondisi:
        1. Body candle > 70% dari range
        2. Volume jauh di atas rata-rata
        3. Close di dekat high/low
        """
        if len(closes) < 3:
            return None

        # Candle terakhir
        body = abs(closes[-1] - opens[-1])
        candle_range = highs[-1] - lows[-1]
        
        if candle_range == 0:
            return None

        body_ratio = body / candle_range
        
        # Close position dalam range
        close_pos = (closes[-1] - lows[-1]) / candle_range

        # Volume check
        avg_vol = np.mean(volumes[-20:-1]) if len(volumes) > 20 else np.mean(volumes[:-1])
        vol_ratio = volumes[-1] / avg_vol if avg_vol > 0 else 1

        # Impulse conditions
        is_strong_body = body_ratio > 0.65
        is_high_volume = vol_ratio > 1.3

        if is_strong_body and is_high_volume:
            if closes[-1] > opens[-1] and close_pos > 0.6:
                return "BULLISH"
            elif closes[-1] < opens[-1] and close_pos < 0.4:
                return "BEARISH"

        # Consecutive impulse (2 candle searah dengan volume tinggi)
        if len(closes) >= 3:
            body2 = abs(closes[-2] - opens[-2])
            range2 = highs[-2] - lows[-2]
            
            if range2 > 0:
                body2_ratio = body2 / range2
                vol2_ratio = volumes[-2] / avg_vol if avg_vol > 0 else 1
                
                # Dua candle bullish berturut kuat
                if (closes[-1] > opens[-1] and closes[-2] > opens[-2] and
                    body_ratio > 0.5 and body2_ratio > 0.5 and
                    (vol_ratio > 1.2 or vol2_ratio > 1.2)):
                    return "BULLISH"
                
                # Dua candle bearish berturut kuat
                if (closes[-1] < opens[-1] and closes[-2] < opens[-2] and
                    body_ratio > 0.5 and body2_ratio > 0.5 and
                    (vol_ratio > 1.2 or vol2_ratio > 1.2)):
                    return "BEARISH"

        return None

    def get_rsi_value(self, candles: list) -> float:
        """Helper: ambil nilai RSI terakhir"""
        if not candles or len(candles) < 15:
            return 50.0
        closes = np.array([c[4] for c in candles])
        rsi_arr = rsi(closes, self.rsi_period)
        return float(rsi_arr[-1])

    def get_ema_values(self, candles: list) -> dict:
        """Helper: ambil EMA values"""
        if not candles or len(candles) < 25:
            return {"ema9": 0, "ema21": 0, "trend": "NEUTRAL"}
        
        closes = np.array([c[4] for c in candles])
        ema9 = ema(closes, 9)[-1]
        ema21 = ema(closes, 21)[-1]
        trend = "BULLISH" if ema9 > ema21 else "BEARISH"
        
        return {"ema9": ema9, "ema21": ema21, "trend": trend}
