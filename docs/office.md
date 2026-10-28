# The office (Phase 5)

A web page where the agents act out every request live: a night-time office floor seen from
above, with the rooms far apart and joined by long glass hallways.

```
   Health Lab ─┐        (uplink · to you)        ┌─ Trading Desk
               └───────────────┼──────────────────┤   ← the main hallway
                         Command Room        Paper Desk
```

| Robot | Room | What's in it |
| --- | --- | --- |
| Health Coach: pink and purple, a sweatband, a heart on its chest | Health Lab | live heart-rate trace, water cooler, treadmill, yoga mat |
| Manager: blue, a headset and a gold tie | Command Room | team status board (a live light per agent), city window, coffee machine |
| Market Scout: a cowl with pointed ears, a cape, a yellow belt | Trading Desk | live candlestick screens, ticker, server racks, the bat-signal, a giant coin |
| Paper Trader: emerald green, an accountant's visor, a pencil behind its ear, a gold $ | Paper Desk | live P/L board (one line per strategy), "PAPER MONEY ONLY" neon, stock-ticker machine, receipts cabinet, safe |

The Paper Trader isn't an AI model: it is the paper-trading rulebook given a robot. It opens the
trades when an alert goes out, flies up its corridor to report each sale to the Scout, and
brings the Scout the books when you ask about your paper trades.

**How a request plays out.** The Manager thinks at its desk, flies out of the Command Room, all
the way down the hallway and into the specialist's room. Only then does the specialist think,
run its tools (a chip shows which, and its desk hologram lights up) and answer in a speech
bubble. Then the Manager carries the answer back along the hallways to the uplink, which beams
it to you. Every event goes onto one timeline (`frontend/src/office/timeline.ts`), so nothing
plays before the step before it has finished.

**Between requests** the robots potter about their rooms every 7–16 seconds. The Health Coach
drinks water, jogs on the treadmill or stretches on the mat. The Manager checks the team board,
has a coffee or watches the city. The Scout watches the charts, works at the servers or stands
in the bat-signal. The Paper Trader checks the P/L board, reads the ticker tape, files receipts
or counts the paper money. A real event interrupts a chore at once, and the robot flies back to its
desk (`frontend/src/office/chores.ts`).

**Camera.** *Overview* shows the whole floor; *Follow* zooms in on whoever is acting (both
robots when one visits another). Phones start in Follow, wider screens in Overview. Speech
bubbles and name tags are drawn at a fixed screen size, so they stay readable at any zoom.

**Changing the look.** Room colours: `THEMES` in `frontend/src/office/art/building.ts`. Robot
colours and accessories: `LOOKS` and the painters in `frontend/src/office/art/robot.ts`. Floor
plan and routes: `frontend/src/office/world.ts`. Everything is painted in code with the Canvas 2D
API (gradients, soft shadows, glows), so there are no image files or licences to manage.

## Live vs. demo

The speech bubbles show your real health numbers, so the live feed is private:

1. In Railway (backend → Variables) add `OFFICE_VIEW_KEY` = a random string of letters and
   digits, 20+ characters. Railway redeploys.
2. Open the office once as `https://<your-office-url>/?key=<that key>`. The page remembers the
   key and removes it from the address bar, so the plain URL works from then on (on that device).

Without the key (or with a wrong one) the page plays a looping **demo with made-up numbers**,
labelled as such. That's the version to share publicly.

## Deploying to Vercel (free)

1. vercel.com → **Add New… → Project** → import the `agent-office` GitHub repo.
2. **Root Directory**: `frontend`. Framework preset: Vite (detected). Leave the build settings as they are.
3. Optional **Environment Variable**: `VITE_API_URL` = your Railway backend URL. The default is
   `https://agent-office-production-d0e3.up.railway.app`, so it's only needed if that changes.
4. **Deploy**. Vercel gives you a URL like `agent-office-xyz.vercel.app` and redeploys on every
   push to `main`.

## Running it locally

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 (demo, or ?key=... for live)
npm test           # routes, the timeline, chores, event rules
```
