# The pixel office (Phase 5)

A web page where the three agents sit at their desks and act out every request live. The
Manager walks over to the Health Coach, the Coach types while its tools run, answers appear in
speech bubbles, and the Manager carries the reply to the door ("to you", i.e. Telegram).

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
npm test           # choreography rules
```
