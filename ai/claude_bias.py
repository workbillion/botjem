"""
CLAUDE AI BIAS
===============
Gunakan Anthropic API untuk market bias analysis
Output: Long/Short/No Trade + Confidence %
"""

import json
import logging
import aiohttp
from typing import Optional

logger = logging.getLogger("CLAUDE_BIAS")


class ClaudeBias:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.anthropic.com/v1/messages"
        self.model = "claude-haiku-4-5-20251001"  # Haiku = cepat + murah
        self.enabled = bool(api_key and api_key != "your_anthropic_key_here")

        if self.enabled:
            logger.info("🤖 Claude AI Bias: ENABLED")
        else:
            logger.warning("🤖 Claude AI Bias: DISABLED (no API key)")

    async def get_bias(self, symbol: str, candles: list, market_state: dict) -> dict:
        """
        Minta bias market dari Claude.
        Returns: {bias, confidence, reason, market_condition}
        """
        if not self.enabled:
            return self._neutral_bias("AI disabled")

        try:
            prompt = self._build_prompt(symbol, candles, market_state)
            
            async with aiohttp.ClientSession() as session:
                headers = {
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                
                payload = {
                    "model": self.model,
                    "max_tokens": 300,
                    "system": (
                        "You are an expert crypto scalping analyst. "
                        "Analyze market data and give a trading bias. "
                        "Always respond with valid JSON only, no extra text."
                    ),
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                }

                async with session.post(
                    self.base_url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=8)  # 8s timeout
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"Claude API error: {resp.status}")
                        return self._neutral_bias("API error")
                    
                    data = await resp.json()
                    text = data["content"][0]["text"]
                    return self._parse_response(text)

        except aiohttp.ClientTimeout:
            logger.debug("Claude API timeout - using neutral bias")
            return self._neutral_bias("timeout")
        except Exception as e:
            logger.error(f"Claude bias error: {e}")
            return self._neutral_bias(str(e))

    def _build_prompt(self, symbol: str, candles: list, market_state: dict) -> str:
        """Build prompt singkat untuk Claude"""
        if not candles or len(candles) < 5:
            recent_data = "insufficient data"
        else:
            # Ambil 10 candle terakhir
            recent = candles[-10:]
            closes = [round(c[4], 4) for c in recent]
            volumes = [round(c[5], 2) for c in recent]
            
            # Price change summary
            price_change = ((closes[-1] - closes[0]) / closes[0]) * 100
            recent_data = (
                f"Closes: {closes}\n"
                f"Volumes: {volumes}\n"
                f"Price change 10 candles: {price_change:+.2f}%"
            )

        return f"""Analyze this crypto futures market for {symbol} (5m chart):

{recent_data}

Market condition: {market_state.get('condition', 'unknown')}
Trending: {market_state.get('trending', False)}
Volatility: {market_state.get('volatility', 'medium')}

Give a SHORT-TERM scalping bias. Respond ONLY with this JSON:
{{
  "bias": "LONG" or "SHORT" or "NO_TRADE",
  "confidence": 0-100,
  "market_condition": "trending" or "ranging" or "volatile",
  "reason": "max 10 words"
}}"""

    def _parse_response(self, text: str) -> dict:
        """Parse JSON response dari Claude"""
        try:
            # Clean up jika ada markdown
            text = text.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            
            data = json.loads(text)
            
            bias = data.get("bias", "NO_TRADE")
            confidence = float(data.get("confidence", 50))
            
            # Validasi
            if bias not in ["LONG", "SHORT", "NO_TRADE"]:
                bias = "NO_TRADE"
            confidence = max(0, min(100, confidence))
            
            logger.debug(f"AI Bias: {bias} {confidence:.0f}% - {data.get('reason', '')}")
            
            return {
                "bias": bias,
                "confidence": confidence,
                "market_condition": data.get("market_condition", "unknown"),
                "reason": data.get("reason", "")
            }
            
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse Claude response: {text[:100]}")
            return self._neutral_bias("parse error")

    def _neutral_bias(self, reason: str = "") -> dict:
        return {
            "bias": "NO_TRADE",
            "confidence": 50,
            "market_condition": "unknown",
            "reason": reason
        }
