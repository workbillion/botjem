# ⚡ AGGRESSIVE CRYPTO SCALPING BOT

> **WARNING**: Bot ini adalah account flipper. $10 → $30 ATAU $10 → $0 dalam 1-2 hari.  
> Gunakan uang yang sanggup kamu kehilangan 100%.

---

## 🧠 Strategi

**Hybrid SMC + Scalping (1m/3m/5m)**

| Komponen | Detail |
|----------|--------|
| SMC | BOS, CHoCH, Order Block, FVG, Liquidity Sweep |
| Scalping | EMA 9/21 cross, RSI (35/65), Volume spike |
| AI Boost | Claude Haiku untuk market bias |
| Mode | Sniper entry + Partial TP + Trailing stop |

**Risk Profile:**
- Risk per trade: 2%–5% (dynamic, berdasarkan confluence score)
- Leverage: 15x default (bisa diubah 10x–20x di config)
- Max posisi: 2 bersamaan
- Daily max loss: 10% → bot stop otomatis
- 5x loss berturut → bot stop hari itu

---

## 📱 Install di Termux

### 1. Install Termux
Download dari F-Droid (BUKAN Play Store, sudah outdated):  
https://f-droid.org/packages/com.termux/

### 2. Setup Termux
```bash
# Update packages
pkg update && pkg upgrade -y

# Install Python
pkg install python python-pip git -y

# Install numpy dependencies
pkg install libopenblas -y
```

### 3. Clone / Upload Bot
```bash
# Option A: Git clone
git clone https://github.com/USERNAME/aggressive-bot.git
cd aggressive-bot

# Option B: Buat manual
mkdir aggressive-bot && cd aggressive-bot
# Upload semua file via Termux:API atau copy paste
```

### 4. Install Python Dependencies
```bash
pip install aiohttp numpy python-dotenv
```

> **Note**: `anthropic` package opsional, hanya jika kamu punya API key.

### 5. Setup Config
```bash
nano config.json
```

Edit bagian ini:
```json
{
  "binance": {
    "api_key": "ISI_API_KEY_BINANCE",
    "api_secret": "ISI_API_SECRET_BINANCE",
    "testnet": false   ← ganti ke false untuk live trading
  },
  "anthropic": {
    "api_key": "ISI_ANTHROPIC_KEY"   ← opsional
  }
}
```

### 6. Setup Binance Futures API

1. Login ke Binance
2. Profile → API Management → Create API
3. Enable: **Futures Trading** (bukan spot)
4. Whitelist IP kamu (opsional tapi recommended)
5. Copy API Key + Secret ke `config.json`

**Untuk testnet:**
- https://testnet.binancefuture.com
- Register akun test, dapat 10,000 USDT virtual

### 7. Run Bot
```bash
# Normal run
python main.py

# Run di background (Termux)
nohup python main.py > logs/run.log 2>&1 &

# Lihat log live
tail -f logs/bot.log

# Stop bot background
kill $(pgrep -f main.py)
```

---

## 📊 Contoh Log Output

```
════════════════════════════════════════════════════════════
  AGGRESSIVE SCALPING BOT - STARTED
  Session: 2024-01-15 09:30:00
════════════════════════════════════════════════════════════
💰 Balance awal: $10.00 USDT
⚙️  Leverage BTCUSDT: 15x
⚙️  Leverage ETHUSDT: 15x
🚀 BOT RUNNING | Symbols: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'] | Scan: 10s

🎯 SIGNAL DETECTED: ETHUSDT
   Direction  : LONG
   Confidence : 78%
   AI Bias    : LONG (72%)
   Reason     : BOS-BULLISH | OB-BULL | EMA-BULLISH | VolSpike
   Size       : 0.03 | Leverage: 15x
   SL         : $2310.50
   TP1 (50%)  : $2338.20
   TP2 (trail): $2356.80
📍 Entry filled @ $2324.30
   SL set @ $2310.50 | TP1(50%) @ $2338.20
✅ ORDER PLACED | ID: 8472910 | #1 today

═══════════════════════════════════════════════════════
💰 POSITION CLOSED: ETHUSDT
   Result     : WIN
   PnL        : +$0.8320
   Reason     : TP2 Hit
   Daily PnL  : +$0.8320
   Balance    : $10.83
   Consec Loss: 0
═══════════════════════════════════════════════════════

═══════════════════════════════════════════════════════
💸 POSITION CLOSED: BTCUSDT
   Result     : LOSS
   PnL        : -$0.4150
   Reason     : SL/TP hit
   Daily PnL  : +$0.4170
   Balance    : $10.42
   Consec Loss: 1
═══════════════════════════════════════════════════════
```

---

## ⚙️ Konfigurasi Lanjutan

### Ubah Aggressiveness
Di `config.json`:
```json
"trading": {
  "leverage": 20,          // Max agresif: 20x
  "min_confidence": 55,    // Turunkan threshold signal
  "scan_interval_seconds": 5,  // Scan lebih cepat
  "max_positions": 3       // Lebih banyak posisi bersamaan
}
```

### Ubah Risk
```json
"risk": {
  "risk_per_trade_min_pct": 3.0,  // Min 3% per trade
  "risk_per_trade_max_pct": 7.0,  // Max 7% per trade
  "tp1_rr": 1.0,                  // TP1 = 1:1
  "tp2_rr": 2.0                   // TP2 = 1:2
}
```

### Ubah Symbol
```json
"trading": {
  "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
}
```

---

## 🏗️ Struktur Project

```
aggressive-bot/
├── main.py              # Entry point utama
├── config.json          # Konfigurasi (JANGAN push ke git!)
├── requirements.txt
├── strategy/
│   ├── smc_fast.py      # SMC: BOS, CHoCH, OB, FVG, Liquidity Sweep
│   └── scalping.py      # EMA, RSI, Volume Spike, Impulse
├── engine/
│   ├── entry.py         # Execute entry + auto SL/TP
│   └── exit.py          # Trailing stop + position monitor
├── risk/
│   └── aggressive_rm.py # Dynamic position sizing
├── ai/
│   └── claude_bias.py   # Claude AI market bias
├── exchange/
│   └── binance_futures.py  # Binance API wrapper
├── utils/
│   ├── logger.py        # Colored logging
│   └── market_filter.py # Market condition detection
└── logs/
    └── bot.log
```

---

## ⚠️ Risk Warning

Bot ini menggunakan leverage tinggi (15x default).  
Dengan $10 modal dan 15x leverage:
- 1 trade bisa profit +$0.50 – $2.00
- 1 trade bisa loss -$0.20 – $0.75
- Kena liquidation jika price bergerak >6.7% melawan posisi

**Rekomendasi:**
1. Coba testnet dulu minimal 3 hari
2. Pantau bot setiap 1-2 jam
3. Jangan tinggal tidur tanpa monitoring awal

---

## 📦 Push ke GitHub

```bash
git init
git add .
git commit -m "Initial aggressive bot"
git remote add origin https://github.com/USERNAME/aggressive-bot.git
git push -u origin main
```

> `config.json` sudah di `.gitignore` — API keys aman tidak ikut push.
