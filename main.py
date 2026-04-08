#!/usr/bin/env python3
"""
AGGRESSIVE CRYPTO SCALPING BOT
================================
Modal: $10 | Target: Flip aggressif
Style: SMC + Scalping Hybrid | HFT Mode
WARNING: High Risk - Account Flipper Bot
"""

import asyncio
import logging
import signal
import sys
import json
import time
from datetime import datetime
from pathlib import Path

# Local imports
from exchange.binance_futures import BinanceFutures
from strategy.smc_fast import SMCFast
from strategy.scalping import ScalpingEngine
from engine.entry import EntryEngine
from engine.exit import ExitEngine
from risk.aggressive_rm import AggressiveRiskManager
from ai.claude_bias import ClaudeBias
from utils.logger import setup_logger
from utils.market_filter import MarketFilter

# ─── Setup ───────────────────────────────────────────────────────────────────
logger = setup_logger("MAIN", "logs/bot.log")

def load_config():
    with open("config.json") as f:
        return json.load(f)

class AggressiveBot:
    def __init__(self):
        self.config = load_config()
        self.running = True
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.trade_count_today = 0
        self.start_balance = None
        self.session_start = datetime.now()

        # Init components
        self.exchange = BinanceFutures(
            api_key=self.config["binance"]["api_key"],
            api_secret=self.config["binance"]["api_secret"],
            testnet=self.config["binance"]["testnet"]
        )
        self.smc = SMCFast()
        self.scalper = ScalpingEngine()
        self.entry_engine = EntryEngine(self.exchange, self.config)
        self.exit_engine = ExitEngine(self.exchange, self.config)
        self.risk_mgr = AggressiveRiskManager(self.config)
        self.claude = ClaudeBias(self.config["anthropic"]["api_key"])
        self.market_filter = MarketFilter()

        logger.info("═" * 60)
        logger.info("  AGGRESSIVE SCALPING BOT - STARTED")
        logger.info(f"  Session: {self.session_start.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("═" * 60)

    async def initialize(self):
        """Setup awal: balance, leverage, dll"""
        balance = await self.exchange.get_balance()
        self.start_balance = balance
        self.risk_mgr.set_balance(balance)
        logger.info(f"💰 Balance awal: ${balance:.2f} USDT")

        # Set leverage untuk semua pair
        for symbol in self.config["trading"]["symbols"]:
            lev = self.config["trading"]["leverage"]
            await self.exchange.set_leverage(symbol, lev)
            logger.info(f"⚙️  Leverage {symbol}: {lev}x")

    async def check_daily_limits(self) -> bool:
        """Cek apakah sudah hit limit harian"""
        balance = await self.exchange.get_balance()
        daily_loss_pct = ((self.start_balance - balance) / self.start_balance) * 100

        if daily_loss_pct >= self.config["risk"]["daily_max_loss_pct"]:
            logger.warning(f"🛑 DAILY MAX LOSS HIT: -{daily_loss_pct:.1f}% → BOT STOP")
            return False

        if self.consecutive_losses >= self.config["risk"]["max_consecutive_losses"]:
            logger.warning(f"🛑 {self.consecutive_losses}x LOSS BERTURUT → BOT STOP HARI INI")
            return False

        return True

    async def run_symbol(self, symbol: str):
        """Main trading loop per symbol"""
        try:
            # Ambil data OHLCV multi-timeframe
            candles_1m = await self.exchange.get_klines(symbol, "1m", 100)
            candles_3m = await self.exchange.get_klines(symbol, "3m", 100)
            candles_5m = await self.exchange.get_klines(symbol, "5m", 100)

            if candles_1m is None or len(candles_1m) < 50:
                return

            # ─── Market Filter ────────────────────────────────────────
            market_state = self.market_filter.analyze(candles_5m)
            if market_state["skip"]:
                logger.debug(f"⏭️  {symbol} skipped: {market_state['reason']}")
                return

            # ─── SMC Analysis ─────────────────────────────────────────
            smc_signal = self.smc.analyze(candles_5m, candles_1m)

            # ─── Scalping Signal ──────────────────────────────────────
            scalp_signal = self.scalper.analyze(candles_1m, candles_3m)

            # ─── Confidence Score ─────────────────────────────────────
            confluence = self.calculate_confluence(smc_signal, scalp_signal, market_state)
            
            if confluence["score"] < self.config["trading"]["min_confidence"]:
                logger.debug(f"📊 {symbol} confluence={confluence['score']:.0f}% < threshold → skip")
                return

            # ─── AI Bias (booster) ────────────────────────────────────
            ai_bias = await self.claude.get_bias(symbol, candles_5m, market_state)
            final_direction = self.merge_signals(confluence, ai_bias)

            if final_direction["direction"] == "NO_TRADE":
                return

            # ─── Cek posisi existing ──────────────────────────────────
            open_positions = await self.exchange.get_open_positions()
            if len(open_positions) >= self.config["trading"]["max_positions"]:
                logger.debug(f"⛔ Max positions ({len(open_positions)}) reached")
                return

            # Jangan double position same symbol
            if any(p["symbol"] == symbol for p in open_positions):
                return

            # ─── Risk Calculation ─────────────────────────────────────
            balance = await self.exchange.get_balance()
            price = await self.exchange.get_price(symbol)
            
            risk_params = self.risk_mgr.calculate_position(
                balance=balance,
                price=price,
                direction=final_direction["direction"],
                candles=candles_1m,
                confluence_score=confluence["score"]
            )

            if not risk_params["valid"]:
                logger.debug(f"❌ Risk check failed: {risk_params['reason']}")
                return

            # ─── EXECUTE ENTRY ────────────────────────────────────────
            logger.info(f"")
            logger.info(f"🎯 SIGNAL DETECTED: {symbol}")
            logger.info(f"   Direction  : {final_direction['direction']}")
            logger.info(f"   Confidence : {confluence['score']:.0f}%")
            logger.info(f"   AI Bias    : {ai_bias['bias']} ({ai_bias['confidence']:.0f}%)")
            logger.info(f"   Reason     : {final_direction['reason']}")
            logger.info(f"   Size       : {risk_params['quantity']} | Leverage: {self.config['trading']['leverage']}x")
            logger.info(f"   SL         : ${risk_params['sl_price']:.4f}")
            logger.info(f"   TP1 (50%)  : ${risk_params['tp1_price']:.4f}")
            logger.info(f"   TP2 (trail): ${risk_params['tp2_price']:.4f}")

            order = await self.entry_engine.execute(
                symbol=symbol,
                direction=final_direction["direction"],
                risk_params=risk_params,
                price=price
            )

            if order and order.get("success"):
                self.trade_count_today += 1
                logger.info(f"✅ ORDER PLACED | ID: {order['order_id']} | #{self.trade_count_today} today")

                # Monitor exit async
                asyncio.create_task(
                    self.exit_engine.monitor_position(
                        symbol=symbol,
                        order=order,
                        risk_params=risk_params,
                        on_close=self.on_position_closed
                    )
                )
            else:
                logger.error(f"❌ Order gagal: {order}")

        except Exception as e:
            logger.error(f"❌ Error run_symbol {symbol}: {e}", exc_info=True)

    def calculate_confluence(self, smc: dict, scalp: dict, market: dict) -> dict:
        """Hitung confluence score dari semua signal"""
        score = 0
        direction = "NO_TRADE"
        reasons = []

        # SMC signals (bobot lebih besar)
        if smc.get("bos"):
            score += 20
            reasons.append(f"BOS-{smc['bos']}")
        if smc.get("choch"):
            score += 15
            reasons.append(f"CHoCH-{smc['choch']}")
        if smc.get("order_block"):
            score += 20
            reasons.append(f"OB-{smc['order_block']}")
        if smc.get("fvg"):
            score += 10
            reasons.append(f"FVG-{smc['fvg']}")
        if smc.get("liquidity_sweep"):
            score += 15
            reasons.append(f"LiqSweep-{smc['liquidity_sweep']}")

        # Scalping signals
        if scalp.get("ema_cross"):
            score += 10
            reasons.append(f"EMA-{scalp['ema_cross']}")
        if scalp.get("rsi_signal"):
            score += 10
            reasons.append(f"RSI-{scalp['rsi_signal']}")
        if scalp.get("volume_spike"):
            score += 15
            reasons.append("VolSpike")

        # Momentum bonus (sniper mode)
        if scalp.get("momentum_impulse"):
            score += 20
            reasons.append("ImpulseCandle")

        # Determine direction
        long_score = smc.get("long_score", 0) + scalp.get("long_score", 0)
        short_score = smc.get("short_score", 0) + scalp.get("short_score", 0)

        if score >= self.config["trading"]["min_confidence"]:
            direction = "LONG" if long_score >= short_score else "SHORT"

        # Market state modifier
        if market.get("trending"):
            score = min(score * 1.1, 100)

        return {
            "score": min(score, 100),
            "direction": direction,
            "reason": " | ".join(reasons[:4])
        }

    def merge_signals(self, confluence: dict, ai_bias: dict) -> dict:
        """Merge confluence + AI bias"""
        direction = confluence["direction"]
        reason = confluence["reason"]

        # AI bisa boost atau veto
        if ai_bias["bias"] != "NO_TRADE":
            if ai_bias["bias"] == direction:
                # Agreement → boost confidence
                reason += f" | AI:{ai_bias['bias']}✓"
            elif ai_bias["confidence"] > 80:
                # AI sangat yakin beda → ikut AI
                direction = ai_bias["bias"]
                reason += f" | AI_OVERRIDE:{ai_bias['bias']}"

        # Jika AI bilang no trade tapi confidence rendah → skip
        if ai_bias["bias"] == "NO_TRADE" and ai_bias["confidence"] > 85:
            direction = "NO_TRADE"
            reason = "AI veto: " + ai_bias.get("reason", "avoid")

        return {"direction": direction, "reason": reason}

    async def on_position_closed(self, symbol: str, pnl: float, reason: str):
        """Callback ketika posisi ditutup"""
        self.daily_pnl += pnl
        balance = await self.exchange.get_balance()

        if pnl > 0:
            self.consecutive_losses = 0
            emoji = "💰"
            result = "WIN"
        else:
            self.consecutive_losses += 1
            emoji = "💸"
            result = "LOSS"

        logger.info(f"")
        logger.info(f"{'═'*55}")
        logger.info(f"{emoji} POSITION CLOSED: {symbol}")
        logger.info(f"   Result     : {result}")
        logger.info(f"   PnL        : ${pnl:+.4f}")
        logger.info(f"   Reason     : {reason}")
        logger.info(f"   Daily PnL  : ${self.daily_pnl:+.4f}")
        logger.info(f"   Balance    : ${balance:.2f}")
        logger.info(f"   Consec Loss: {self.consecutive_losses}")
        logger.info(f"{'═'*55}")

    async def run(self):
        """Main loop"""
        await self.initialize()

        scan_interval = self.config["trading"]["scan_interval_seconds"]
        symbols = self.config["trading"]["symbols"]

        logger.info(f"🚀 BOT RUNNING | Symbols: {symbols} | Scan: {scan_interval}s")
        logger.info(f"⚡ MODE: AGGRESSIVE SCALPING")

        while self.running:
            try:
                # Cek daily limits
                if not await self.check_daily_limits():
                    logger.info("😴 Bot istirahat, cek lagi besok")
                    await asyncio.sleep(3600)
                    continue

                # Manage existing positions (trailing stop, partial TP)
                await self.exit_engine.manage_open_positions(self.on_position_closed)

                # Scan semua symbol
                tasks = [self.run_symbol(sym) for sym in symbols]
                await asyncio.gather(*tasks, return_exceptions=True)

                # Status update setiap 10 menit
                if int(time.time()) % 600 < scan_interval:
                    balance = await self.exchange.get_balance()
                    positions = await self.exchange.get_open_positions()
                    pnl_pct = ((balance - self.start_balance) / self.start_balance) * 100
                    logger.info(f"📈 STATUS | Balance: ${balance:.2f} | PnL: {pnl_pct:+.1f}% | "
                               f"Trades: {self.trade_count_today} | Open: {len(positions)}")

                await asyncio.sleep(scan_interval)

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Main loop error: {e}", exc_info=True)
                await asyncio.sleep(5)

        await self.shutdown()

    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("🛑 Shutting down bot...")
        try:
            positions = await self.exchange.get_open_positions()
            if positions:
                logger.info(f"⚠️  {len(positions)} posisi masih buka - pertimbangkan close manual")
        except Exception:
            pass
        
        balance = await self.exchange.get_balance() if self.start_balance else 0
        if self.start_balance:
            total_pnl_pct = ((balance - self.start_balance) / self.start_balance) * 100
            logger.info(f"📊 SESSION SUMMARY")
            logger.info(f"   Start balance : ${self.start_balance:.2f}")
            logger.info(f"   End balance   : ${balance:.2f}")
            logger.info(f"   Total PnL     : {total_pnl_pct:+.1f}%")
            logger.info(f"   Total trades  : {self.trade_count_today}")
        logger.info("Bot stopped. Goodbye! 👋")


def main():
    bot = AggressiveBot()
    
    def handle_signal(sig, frame):
        logger.info(f"Signal {sig} received")
        bot.running = False

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    asyncio.run(bot.run())


if __name__ == "__main__":
    main()
