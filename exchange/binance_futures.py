"""
BINANCE FUTURES EXCHANGE
=========================
Async wrapper untuk Binance USDT-M Futures API
"""

import asyncio
import hashlib
import hmac
import logging
import time
import urllib.parse
from typing import Optional, List
import aiohttp

logger = logging.getLogger("BINANCE")

LIVE_BASE = "https://fapi.binance.com"
TEST_BASE = "https://testnet.binancefuture.com"


class BinanceFutures:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = TEST_BASE if testnet else LIVE_BASE
        self.session: Optional[aiohttp.ClientSession] = None
        self.testnet = testnet
        
        mode = "TESTNET" if testnet else "LIVE"
        logger.info(f"🔗 Binance Futures [{mode}]: {self.base_url}")

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={"X-MBX-APIKEY": self.api_key},
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self.session

    def _sign(self, params: dict) -> dict:
        """Add timestamp + signature"""
        params["timestamp"] = int(time.time() * 1000)
        query = urllib.parse.urlencode(params)
        sig = hmac.new(
            self.api_secret.encode(),
            query.encode(),
            hashlib.sha256
        ).hexdigest()
        params["signature"] = sig
        return params

    async def _get(self, endpoint: str, params: dict = None, signed: bool = False) -> Optional[dict]:
        """GET request"""
        session = await self._get_session()
        p = params or {}
        if signed:
            p = self._sign(p)
        try:
            async with session.get(f"{self.base_url}{endpoint}", params=p) as resp:
                data = await resp.json()
                if isinstance(data, dict) and "code" in data and data["code"] < 0:
                    logger.error(f"Binance GET error {endpoint}: {data}")
                    return None
                return data
        except Exception as e:
            logger.error(f"GET {endpoint} error: {e}")
            return None

    async def _post(self, endpoint: str, params: dict) -> Optional[dict]:
        """POST request (signed)"""
        session = await self._get_session()
        p = self._sign(params)
        try:
            async with session.post(f"{self.base_url}{endpoint}", data=p) as resp:
                data = await resp.json()
                if isinstance(data, dict) and "code" in data and data["code"] < 0:
                    logger.error(f"Binance POST error {endpoint}: {data}")
                    return None
                return data
        except Exception as e:
            logger.error(f"POST {endpoint} error: {e}")
            return None

    async def _delete(self, endpoint: str, params: dict) -> Optional[dict]:
        """DELETE request (signed)"""
        session = await self._get_session()
        p = self._sign(params)
        try:
            async with session.delete(f"{self.base_url}{endpoint}", params=p) as resp:
                return await resp.json()
        except Exception as e:
            logger.error(f"DELETE {endpoint} error: {e}")
            return None

    # ─── Public Methods ───────────────────────────────────────────────────────

    async def get_balance(self) -> float:
        """Ambil USDT balance"""
        data = await self._get("/fapi/v2/balance", signed=True)
        if data:
            for asset in data:
                if asset.get("asset") == "USDT":
                    return float(asset.get("availableBalance", 0))
        return 0.0

    async def get_price(self, symbol: str) -> float:
        """Ambil harga terakhir"""
        data = await self._get("/fapi/v1/ticker/price", {"symbol": symbol})
        return float(data["price"]) if data else 0.0

    async def get_klines(self, symbol: str, interval: str, limit: int = 100) -> Optional[list]:
        """
        Ambil candlestick data.
        Returns list of [timestamp, open, high, low, close, volume, ...]
        """
        data = await self._get("/fapi/v1/klines", {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        })
        
        if not data:
            return None
        
        # Format: [timestamp, open, high, low, close, volume, ...]
        return [[
            int(c[0]),    # timestamp
            float(c[1]),  # open
            float(c[2]),  # high
            float(c[3]),  # low
            float(c[4]),  # close
            float(c[5])   # volume
        ] for c in data]

    async def get_open_positions(self) -> List[dict]:
        """Ambil semua posisi yang sedang buka"""
        data = await self._get("/fapi/v2/positionRisk", signed=True)
        if not data:
            return []
        
        # Filter hanya yang punya posisi aktif
        return [p for p in data if abs(float(p.get("positionAmt", 0))) > 0]

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage untuk symbol"""
        result = await self._post("/fapi/v1/leverage", {
            "symbol": symbol,
            "leverage": leverage
        })
        return result is not None

    async def set_margin_type(self, symbol: str, margin_type: str = "ISOLATED") -> bool:
        """Set ISOLATED atau CROSSED margin"""
        result = await self._post("/fapi/v1/marginType", {
            "symbol": symbol,
            "marginType": margin_type
        })
        return result is not None

    async def place_market_order(self, symbol: str, side: str, quantity: float,
                                  reduce_only: bool = False) -> Optional[dict]:
        """Place market order"""
        params = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": quantity,
        }
        if reduce_only:
            params["reduceOnly"] = "true"
        
        return await self._post("/fapi/v1/order", params)

    async def place_stop_order(self, symbol: str, side: str, quantity: float,
                                stop_price: float) -> Optional[dict]:
        """Place Stop Market order (SL)"""
        params = {
            "symbol": symbol,
            "side": side,
            "type": "STOP_MARKET",
            "stopPrice": round(stop_price, 4),
            "quantity": quantity,
            "reduceOnly": "true",
            "closePosition": "false"
        }
        return await self._post("/fapi/v1/order", params)

    async def place_take_profit_order(self, symbol: str, side: str, quantity: float,
                                       price: float) -> Optional[dict]:
        """Place Take Profit Market order"""
        params = {
            "symbol": symbol,
            "side": side,
            "type": "TAKE_PROFIT_MARKET",
            "stopPrice": round(price, 4),
            "quantity": quantity,
            "reduceOnly": "true"
        }
        return await self._post("/fapi/v1/order", params)

    async def cancel_order(self, symbol: str, order_id: int) -> Optional[dict]:
        """Cancel order by ID"""
        return await self._delete("/fapi/v1/order", {
            "symbol": symbol,
            "orderId": order_id
        })

    async def cancel_all_orders(self, symbol: str) -> Optional[dict]:
        """Cancel semua open orders untuk symbol"""
        return await self._delete("/fapi/v1/allOpenOrders", {"symbol": symbol})

    async def get_account_info(self) -> Optional[dict]:
        """Ambil info akun lengkap"""
        return await self._get("/fapi/v2/account", signed=True)

    async def get_24h_stats(self, symbol: str) -> Optional[dict]:
        """Ambil 24h stats untuk volume check"""
        return await self._get("/fapi/v1/ticker/24hr", {"symbol": symbol})

    async def close(self):
        """Close session"""
        if self.session and not self.session.closed:
            await self.session.close()
