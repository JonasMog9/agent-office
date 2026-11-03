"""The eval questions: what the owner might really text the bot, each with the specialist and
tools a correct run uses. Written against the eval world (``world.py``): a runner who is
run down today (red recovery, short sleep), training for a half marathon, and a Market
Scout that flagged two coins (RUN, DUD) this week.

``tools_any``: at least one must be called; ``tools_all``: every one must be. ``adjust_plan``
is off limits unless a case asks for a new plan, since it rewrites the plan.
"""

from app.evals.grade import Case
from app.evals.world import DUD_MINT, MEH_MINT, RUG_MINT, RUN_MINT

H, S, NONE = "health_coach", "market_scout", "none"
RECOVERY = ("get_recovery",)
SLEEP = ("get_sleep",)
PLAN = ("get_plan",)
LOAD = ("get_training_load",)
PREDICT = ("predict_race",)
UNKNOWN = "4Nd1mBQtrMJVYVfKf2PJy9NZUZdTAsp7D4xWLs4gDB4T"  # valid format, not in the world

CASES: list[Case] = [
    # --- recovery and readiness
    Case("recovery-today", "How recovered am I today?", H, RECOVERY),
    Case("ready-to-train", "How ready am I to train today?", H, ("get_recovery", "get_plan")),
    Case("why-red", "Why is my recovery red today?", H, RECOVERY),
    Case("hrv", "What's my HRV compared to normal?", H, RECOVERY),
    Case("resting-hr", "Is my resting heart rate up?", H, RECOVERY),
    Case("hard-session", "Should I do a hard workout today?", H, ("get_recovery", "get_plan")),
    Case("feel-awful", "I feel awful this morning, what do the numbers say?", H, RECOVERY),
    Case("recovery-yesterday", "What was my recovery yesterday?", H, ("get_recovery", "get_trend")),
    # --- sleep
    Case("sleep-last-night", "How did I sleep last night?", H, SLEEP),
    Case("sleep-debt", "How much sleep debt do I have?", H, SLEEP),
    Case("sleep-tonight", "How much should I sleep tonight?", H, SLEEP),
    Case("sleep-week", "Has my sleep been getting worse this week?", H, ("get_trend", "get_sleep")),
    # --- strain and load
    Case("strain-yesterday", "What was my strain yesterday?", H, ("get_strain", "get_trend")),
    Case("load", "What's my training load right now?", H, LOAD),
    Case("overtraining", "Am I overtraining?", H, ("get_training_load", "get_recovery")),
    Case("acwr", "What's my acute to chronic workload ratio?", H, LOAD),
    Case(
        "fitness-fatigue", "Is my fitness going up or down?", H, ("get_training_load", "get_trend")
    ),
    Case(
        "weekly-km", "How many km a week have I been running?", H, ("get_training_load", "get_plan")
    ),
    Case("trend-7", "Show me my last 7 days.", H, ("get_trend",)),
    Case("trend-month", "How has my recovery trended over the last month?", H, ("get_trend",)),
    # --- races and zones
    Case("predict-5k", "What could I run a 5K in right now?", H, PREDICT),
    Case("predict-10k", "What's my predicted 10K time?", H, PREDICT),
    Case("predict-half", "How fast could I run a half marathon?", H, PREDICT),
    Case("predict-marathon", "Could I break 3:30 in a marathon?", H, PREDICT),
    Case("zones-hr", "What are my heart rate zones?", H, ("get_zones",)),
    Case("zones-pace", "What pace should my easy runs be?", H, ("get_zones", "get_plan")),
    # --- the plan
    Case("plan-today", "What's my workout today?", H, PLAN),
    Case("plan-week", "What does the rest of my week look like?", H, PLAN),
    Case("pain", "My hip hurts a bit, should I still run today?", H, PLAN, note="pain=true"),
    Case("illness", "Do I look like I'm getting sick?", H, ("get_warnings", "get_recovery")),
    Case("injury-risk", "Any injury warnings I should know about?", H, ("get_warnings",)),
    Case(
        "new-plan",
        "Build me a new plan for a 10K on 2027-02-14, 4 runs a week.",
        H,
        tools_all=("adjust_plan",),
        tools_never=(),
        mutates=True,
    ),
    # --- Market Scout
    Case("anything-up", "Anything up in the market?", S, ("latest_scan",)),
    Case("runners", "Any potential runners today?", S, ("latest_scan",)),
    Case("near-miss", "What came closest to alerting in the last scan?", S, ("latest_scan",)),
    Case("alerts-week", "Which coins did you flag this week?", S, ("latest_scan",)),
    Case("check-pass", f"check {RUN_MINT}", S, ("check_token",)),
    Case("check-rug", f"Is this safe? {RUG_MINT}", S, ("check_token",)),
    Case("check-meh", f"Rug check {MEH_MINT} please", S, ("check_token",)),
    Case("check-dud", f"What about {DUD_MINT}?", S, ("check_token",)),
    Case("check-unknown", f"check {UNKNOWN}", S, ("check_token",)),
    Case("paper", "How are my paper trades?", S, ("paper_trades",)),
    Case("best-strategy", "Which paper strategy is winning?", S, ("paper_trades",)),
    Case("moon-bag", "How is the moon bag strategy doing?", S, ("paper_trades",)),
    Case("open-trades", "Which paper trades are still open?", S, ("paper_trades",)),
    Case("should-buy", f"Should I buy {RUN_MINT}?", S, ("check_token", "latest_scan")),
    # --- the Manager on its own
    Case("hello", "hey", NONE, tools_never=()),
    Case("what-can-you-do", "What can you do?", NONE, tools_never=()),
    Case("thanks", "thanks, that's all", NONE, tools_never=()),
    # --- tricky ones
    Case(
        "no-data-day",
        "What was my recovery on 2019-06-01?",
        H,
        ("get_recovery",),
        note="no data that day: must say so, not invent a score",
    ),
    Case(
        "made-up-metric",
        "What's my lactate threshold heart rate?",
        H,
        note="no tool gives it: must say so, not estimate",
    ),
    Case(
        "both",
        "How recovered am I, and is anything up in crypto?",
        "both",
        tools_all=("get_recovery", "latest_scan"),
        note="needs both specialists",
    ),
]
