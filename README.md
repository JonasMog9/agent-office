# agent-office
A cloud-hosted multi-agent system with a 2D pixel-art office. Text the Manager on Telegram and it hands the job to specialist AI agents: a running coach that works from Apple Watch and Strava data (readiness, training load, race-time predictions) and a market scout. Built with Python, the Claude API, FastAPI and WebSockets, and deployed on Railway.

See [PLAN.md](PLAN.md) for the build plan and [CLAUDE.md](CLAUDE.md) for the stack and repo rules.

## Local development

```bash
cp .env.example .env            # fill in real values; .env is gitignored

# Backend (Python 3.12)
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload   # http://localhost:8000/health
ruff check . && ruff format --check . && pytest

# Frontend (Node 22)
cd frontend
npm install
npm run dev                     # http://localhost:5173
```
