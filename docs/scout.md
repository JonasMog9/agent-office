# The Market Scout (Phase 6)

The Scout watches brand-new crypto coins and messages you on Telegram **only** when one looks
like a potential runner: at most two days old, trading huge, real volume, and passing every
rug test. Most days nothing qualifies, so most days you hear nothing.

It is **read-only**. There's no wallet, no exchange keys and nothing that can buy or sell.
Every message ends with "Not financial advice."

## How a coin gets through

Every 10 minutes the scanner pulls the trending and top-volume pools on Solana (Base and
Ethereum can be switched on) from GeckoTerminal (CoinGecko's DEX data). Coins at most 48 hours old go through two
gates, and **both** must pass.

**1. The market screen** (`backend/app/scout/screen.py`):

| Rule | Must be |
| --- | --- |
| Age | ≤ 48 h |
| 24 h volume | ≥ $1M |
| Liquidity | ≥ $75k |
| Distinct buyers (24 h) | ≥ 500 |
| Turnover (volume ÷ liquidity) | ≥ 3× |
| Average trade | ≤ $3,000 (a few wallets churning fake volume fail this) |
| Still going | last hour's volume ≥ half its average hourly volume |
| Not dumping | 1 h change ≥ −25%, 6 h change ≥ −40% |
| Buy side | buyers ≥ 0.8 × sellers |
| Still early | FDV ≤ $30M |

**2. The rug tests** (`backend/app/scout/rug.py`). On Base and Ethereum they come from GoPlus:
contract verified, not a honeypot, buy and sell tax ≤ 10%, no minting, no owner tricks, ≥ 90%
of liquidity locked or burned, top 10 holders ≤ 30% and creator ≤ 5%. On Solana they come from
RugCheck: mint and freeze authority revoked, not flagged as rugged, ≥ 90% of liquidity locked
or burned, top 10 holders ≤ 30%, transfer fee ≤ 10% and no "danger" flags. **If a test can't
get its data, it fails.** Passing every test still doesn't make a coin safe.

Each coin alerts at most once, and at most 3 alerts go out in 24 hours.

## Paper trading

The Scout never trades real money. Every alert opens a **pretend $10 trade** at the price when
the alert went out, so you can see whether the alerts would have made money. Each scan
re-prices open trades and sells at the first rule that fires:

| Rule | Sells when |
| --- | --- |
| Take profit | price ≥ 2× the entry |
| Stop loss | price ≤ half the entry |
| Rug | the pool's liquidity drops below $1,000 |
| Time | 3 days after the entry |

It sells at the price it actually sees (a coin can jump past 2× between checks), and charges
2% fees and slippage on the way in and out. When a trade closes you get a short Telegram
message with its result and the running total. The rules are in `backend/app/scout/paper.py`.

## Asking it things

Message the bot:

- "Anything up?" or "Any runners?" gives the latest scan, its closest near misses and what
  they failed, plus any alerts from the last week.
- "Check <Solana address>" runs the screen and every rug test on that coin now.
- "How are my paper trades?" gives the win rate, total P/L, best and worst calls, and open
  trades.

## Settings (Railway → backend → Variables)

| Variable | Default | What it does |
| --- | --- | --- |
| `SCOUT_ENABLED` | `true` | `false` stops the scans |
| `SCOUT_CHAINS` | `solana` | which chains to scan (`base` and `eth` work too) |
| `SCOUT_SCAN_MINUTES` | `10` | how often |
| `SCOUT_MIN_VOLUME_USD` | `1000000` | the volume bar ("crazy volume") |
| `SCOUT_MAX_ALERTS_PER_DAY` | `3` | safety cap on messages |

The data sources are free public APIs that need no keys.
