"""
EXIT ENGINE
============
Monitor posisi: trailing stop, partial TP, force close
"""

import asyncio
import logging
import time
from typing import Callable, Optional

logger = logging.getLogger("EXIT")


class ExitEngine:
    def __init__(self, exchange, config: dict):
        self.exchange = exchange
        self.config = config
        self.active_monitors = {}  # symbol -> monitor task

    async def monitor_position(self, symbol: str, order: dict, risk_params: dict, on_close: Callable):
        """
        Monitor satu posisi: trailing stop + waktu max hold
        """
        direction = order["direction"]
        fill_price = order["fill_price"]
        sl_price = order["sl_price"]
        tp1_price = order["tp1_price"]
        tp2_price = order["tp2_price"]
        quantity = order["remaining_quantity"]
        trailing_dist = risk_params.get("trailing_distance", 0)

        highest_price = fill_price  # untuk LONG
        lowest_price = fill_price   # untuk SHORT
        tp1_hit = False
        start_time = time.time()
        max_hold_seconds = self.config["trading"].get("max_hold_minutes", 60) * 60

        logger.info(f"👁️  Monitoring {symbol} {direction} | Trail: {trailing_dist:.4f}")

        while True:
            try:
                # Cek apakah posisi masih ada
                positions = await self.exchange.get_open_positions()
                pos = next((p for p in positions if p["symbol"] == symbol), None)

                if not pos:
                    # Posisi sudah tutup (kena SL/TP otomatis)
                    pnl = self._estimate_pnl(direction, fill_price,
                                             tp1_price if tp1_hit else sl_price,
                                             order["quantity"])
                    reason = "TP1 hit" if tp1_hit else "SL/TP hit"
                    await on_close(symbol, pnl, reason)
                    return

                current_price = float(pos.get("markPrice", 0))
                unrealized_pnl = float(pos.get("unrealizedProfit", 0))

                # ─── TP1 Check ────────────────────────────────────────
                if not tp1_hit:
                    if direction == "LONG" and current_price >= tp1_price:
                        tp1_hit = True
                        logger.info(f"🎯 TP1 HIT {symbol} @ ${current_price:.4f} | PnL: ${unrealized_pnl:.4f}")
                        # Trailing stop aktif untuk sisa posisi
                        trailing_dist = abs(tp1_price - fill_price) * 0.5  # Trail = 50% dari TP1 distance

                    elif direction == "SHORT" and current_price <= tp1_price:
                        tp1_hit = True
                        logger.info(f"🎯 TP1 HIT {symbol} @ ${current_price:.4f} | PnL: ${unrealized_pnl:.4f}")
                        trailing_dist = abs(fill_price - tp1_price) * 0.5

                # ─── Trailing Stop ────────────────────────────────────
                if tp1_hit and trailing_dist > 0:
                    if direction == "LONG":
                        if current_price > highest_price:
                            highest_price = current_price
                            new_sl = highest_price - trailing_dist
                            if new_sl > sl_price:
                                sl_price = new_sl
                                await self._update_sl(symbol, order, sl_price, quantity, "SELL")
                        
                        if current_price <= sl_price:
                            await self._force_close(symbol, quantity, "SELL")
                            pnl = self._estimate_pnl(direction, fill_price, sl_price, quantity)
                            await on_close(symbol, unrealized_pnl, "Trailing Stop Hit")
                            return

                    elif direction == "SHORT":
                        if current_price < lowest_price:
                            lowest_price = current_price
                            new_sl = lowest_price + trailing_dist
                            if new_sl < sl_price:
                                sl_price = new_sl
                                await self._update_sl(symbol, order, sl_price, quantity, "BUY")
                        
                        if current_price >= sl_price:
                            await self._force_close(symbol, quantity, "BUY")
                            await on_close(symbol, unrealized_pnl, "Trailing Stop Hit")
                            return

                # ─── Max Hold Time ────────────────────────────────────
                elapsed = time.time() - start_time
                if elapsed > max_hold_seconds:
                    logger.info(f"⏰ Max hold time reached for {symbol}, closing...")
                    close_side = "SELL" if direction == "LONG" else "BUY"
                    await self._force_close(symbol, float(pos["positionAmt"]), close_side)
                    await on_close(symbol, unrealized_pnl, "Max Hold Time")
                    return

                # ─── TP2 Check ────────────────────────────────────────
                if tp1_hit:
                    if direction == "LONG" and current_price >= tp2_price:
                        await self._force_close(symbol, quantity, "SELL")
                        await on_close(symbol, unrealized_pnl, "TP2 Hit")
                        return
                    elif direction == "SHORT" and current_price <= tp2_price:
                        await self._force_close(symbol, quantity, "BUY")
                        await on_close(symbol, unrealized_pnl, "TP2 Hit")
                        return

                await asyncio.sleep(5)  # Check setiap 5 detik

            except Exception as e:
                logger.error(f"Monitor error {symbol}: {e}")
                await asyncio.sleep(10)

    async def manage_open_positions(self, on_close: Callable):
        """
        Kelola semua posisi yang sedang buka.
        Dipanggil dari main loop untuk update trailing stop.
        """
        try:
            positions = await self.exchange.get_open_positions()
            for pos in positions:
                symbol = pos["symbol"]
                pnl = float(pos.get("unrealizedProfit", 0))
                
                # Emergency: kalau unrealized loss > 30% dari margin → force close
                margin = float(pos.get("initialMargin", 1))
                if margin > 0 and pnl < 0:
                    loss_pct = abs(pnl) / margin * 100
                    if loss_pct > self.config["risk"].get("emergency_close_pct", 35):
                        logger.warning(f"🚨 EMERGENCY CLOSE {symbol}: loss {loss_pct:.1f}%")
                        side = "SELL" if float(pos["positionAmt"]) > 0 else "BUY"
                        qty = abs(float(pos["positionAmt"]))
                        await self._force_close(symbol, qty, side)
                        await on_close(symbol, pnl, "Emergency Close")

        except Exception as e:
            logger.error(f"manage_open_positions error: {e}")

    async def _force_close(self, symbol: str, quantity: float, side: str):
        """Force close position via market order"""
        try:
            result = await self.exchange.place_market_order(
                symbol=symbol,
                side=side,
                quantity=abs(quantity),
                reduce_only=True
            )
            logger.info(f"🔒 Force closed {symbol} {side} qty={quantity}")
            return result
        except Exception as e:
            logger.error(f"Force close error {symbol}: {e}")

    async def _update_sl(self, symbol: str, order: dict, new_sl: float, quantity: float, side: str):
        """Update stop loss order"""
        try:
            # Cancel old SL
            if order.get("sl_order_id"):
                await self.exchange.cancel_order(symbol, order["sl_order_id"])

            # Place new SL
            new_sl_order = await self.exchange.place_stop_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                stop_price=new_sl
            )
            if new_sl_order:
                order["sl_order_id"] = new_sl_order.get("orderId")
                logger.debug(f"📌 SL updated {symbol} → ${new_sl:.4f}")
        except Exception as e:
            logger.error(f"Update SL error: {e}")

    def _estimate_pnl(self, direction: str, entry: float, exit_price: float, quantity: float) -> float:
        """Estimate PnL (tanpa leverage untuk kalkulasi sederhana)"""
        if direction == "LONG":
            return (exit_price - entry) * quantity
        else:
            return (entry - exit_price) * quantity
