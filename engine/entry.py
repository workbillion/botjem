"""
ENTRY ENGINE
=============
Execute entry orders: market + limit
Auto SL/TP placement
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger("ENTRY")


class EntryEngine:
    def __init__(self, exchange, config: dict):
        self.exchange = exchange
        self.config = config

    async def execute(self, symbol: str, direction: str, risk_params: dict, price: float) -> Optional[dict]:
        """
        Execute entry order dengan SL/TP otomatis.
        Returns order result dict.
        """
        try:
            side = "BUY" if direction == "LONG" else "SELL"
            quantity = risk_params["quantity"]
            sl_price = risk_params["sl_price"]
            tp1_price = risk_params["tp1_price"]
            tp2_price = risk_params["tp2_price"]

            # ─── Market Order Entry ───────────────────────────────────
            entry_order = await self.exchange.place_market_order(
                symbol=symbol,
                side=side,
                quantity=quantity
            )

            if not entry_order or not entry_order.get("orderId"):
                logger.error(f"Entry order failed for {symbol}")
                return {"success": False, "error": "Order placement failed"}

            order_id = entry_order["orderId"]
            fill_price = float(entry_order.get("avgPrice", price))
            logger.info(f"📍 Entry filled @ ${fill_price:.4f}")

            # ─── Stop Loss Order ──────────────────────────────────────
            sl_side = "SELL" if direction == "LONG" else "BUY"
            sl_order = await self.exchange.place_stop_order(
                symbol=symbol,
                side=sl_side,
                quantity=quantity,
                stop_price=sl_price
            )

            # ─── TP1 (50% partial close) ──────────────────────────────
            tp_quantity = round(quantity * 0.5, self._get_precision(symbol))
            tp1_order = await self.exchange.place_take_profit_order(
                symbol=symbol,
                side=sl_side,
                quantity=tp_quantity,
                price=tp1_price
            )

            logger.info(f"   SL set @ ${sl_price:.4f} | TP1(50%) @ ${tp1_price:.4f}")

            return {
                "success": True,
                "order_id": order_id,
                "symbol": symbol,
                "direction": direction,
                "quantity": quantity,
                "fill_price": fill_price,
                "sl_price": sl_price,
                "tp1_price": tp1_price,
                "tp2_price": tp2_price,
                "sl_order_id": sl_order.get("orderId") if sl_order else None,
                "tp1_order_id": tp1_order.get("orderId") if tp1_order else None,
                "remaining_quantity": quantity - tp_quantity,
                "trailing_active": False,
                "trailing_distance": risk_params.get("trailing_distance", 0)
            }

        except Exception as e:
            logger.error(f"Entry execute error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def _get_precision(self, symbol: str) -> int:
        """Get quantity decimal precision per symbol"""
        precisions = {
            "BTCUSDT": 3,
            "ETHUSDT": 2,
            "SOLUSDT": 1,
            "BNBUSDT": 2,
            "XRPUSDT": 0,
            "DOGEUSDT": 0,
        }
        for sym, prec in precisions.items():
            if sym in symbol:
                return prec
        return 2
