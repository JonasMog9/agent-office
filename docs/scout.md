# The Market Scout (Phase 6)

The Scout watches brand-new crypto coins and messages you on Telegram **only** when one looks
like a potential runner: at most two days old, trading huge, real volume, and passing every
rug test. Most days nothing qualifies, so most days you hear nothing.

It is **read-only**. There's no wallet, no exchange keys and nothing that can buy or sell.
Every message ends with "Not financial advice."

## How a coin gets through

Every 10 minutes the scanner pulls the trending and top-volume pools on Solana, Base and
Ethereum from GeckoTerminal (CoinGecko's DEX data). Coins at most 48 hours old go through two
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

## Paper trading: three strategies

The Scout never trades real money. Every alert opens a **pretend $10 trade with each of three
strategies** at the price when the alert went out. They buy the same coins at the same price
and only sell differently, so the stats page shows which way of selling would have made money.

| # | Strategy | Sells |
| --- | --- | --- |
| 1 | **Quick 2×** | everything at 2×. Stop at −50%, sell after 3 days |
| 2 | **Runner** | no fixed target: once it has reached 2×, everything when it falls 30% below its peak (a 5× that fades sells near 3.5×). Stop at −50% before that, sell after 7 days |
| 3 | **Moon bag** | half at 2× (the stake back), a quarter at 5×, and the last quarter rides for 10× or more with a 50% trailing stop, up to 14 days. Stop at −50% before the first sale |

All three also sell whatever is left if the pool's liquidity drops below $1,000 (a rug).

**Why these three.** New coins' returns are extremely skewed: most fall 90% or more from their
peak, and a few run far past 2×. Selling everything at 2× caps the winners that have to pay
for all the losers. Traders' usual advice is to take the stake out around 2× and let a small
"moon bag" ride, or to trail a stop 25–35% under the peak instead of using a fixed target. I
found no independent backtests of these rules, which is why they run side by side on the same
alerts here.

**Honest prices.** Each strategy sells at the price a scan actually sees (a coin can jump past
2× between checks, or crash through the stop), and pays 2% fees and slippage on the way in and
out. Alerts from before the Runner and Moon bag existed were replayed on GeckoTerminal's
15-minute candles, using closing prices only (not the highs, which a 10-minute check would
often miss).

**Messages.** Once all three of a coin's trades have closed, you get one Telegram message with
how each did and the running totals. In the office, the **Paper Trader** robot (no AI: it is
this rulebook given a body) opens the trades when an alert goes out, flies up to the Scout to
report each sale, and brings the Scout the books when you ask. The rules are in
`backend/app/scout/paper.py`.

## Asking it things

Message the bot:

- "Anything up?" or "Any runners?" gives the latest scan, its closest near misses and what
  they failed, plus any alerts from the last week.
- "Check <Solana address>" runs the screen and every rug test on that coin now.
- "How are my paper trades?" or "which strategy is winning?" gives each strategy's total
  P/L and win rate, and its open trades.

## Settings (Railway → backend → Variables)

| Variable | Default | What it does |
| --- | --- | --- |
| `SCOUT_ENABLED` | `true` | `false` stops the scans |
| `SCOUT_CHAINS` | `solana,base,eth` | which chains to scan |
| `SCOUT_SCAN_MINUTES` | `10` | how often |
| `SCOUT_MIN_VOLUME_USD` | `1000000` | the volume bar ("crazy volume") |
| `SCOUT_MAX_ALERTS_PER_DAY` | `3` | safety cap on messages |

The data sources are free public APIs that need no keys.
