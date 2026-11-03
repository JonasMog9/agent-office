import json

from app.evals.grade import Case, Trace, grade, numbers, ungrounded

TOOL = json.dumps(
    {
        "recovery": 8.0,
        "label": "red",
        "breakdown": {"components": [{"name": "hrv", "value": 48.6, "baseline": 56}]},
        "asleep_last_night": "6 h 45 min",
        "sleep_debt_min": 409,
        "predicted": "39:50",
        "volume_24h": "$3.0M",
        "fraction": 0.42,
    }
)


def test_numbers_understand_money_percent_and_scale():
    got = [(n.value, n.decimals) for n in numbers("$3.1M volume, 42%, 1,250 buyers, −16 form")]
    assert got == [(3.1e6, 1), (42.0, 0), (1250.0, 0), (16.0, 0)]


def test_dates_and_clock_times_are_not_numbers():
    assert numbers("On 2026-11-03 and Nov 3 you ran") == []
    assert [n.value for n in numbers("a 4:57/km pace for 12 km")] == [12.0]


def test_numbers_backed_by_tools_are_grounded_even_when_rounded():
    answer = "Recovery 8% (red). HRV 49 vs 56. You slept 6 h 45 min; debt 6 h 49 min. 10K in 39:50."
    assert ungrounded(answer, [TOOL]) == []
    assert ungrounded("Volume was $3M and 42% of it came from buys.", [TOOL]) == []


def test_invented_numbers_are_caught():
    answer = "Recovery 8%, HRV 63 vs 56, and your VO2max is 58.2. A 10K in 41:10."
    assert ungrounded(answer, [TOOL]) == ["41:10", "63", "58.2"]


def test_small_counts_and_numbers_from_the_question_are_fine():
    assert ungrounded("3 strategies, 2× target, 4 runs a week.", []) == []
    assert (
        ungrounded("A plan for your 10K on 2027-02-14 with 21 days of base.", [], "21 days") == []
    )


def trace(answer: str, specialists=("health_coach",), tools=("get_recovery",)) -> Trace:
    return Trace(answer, list(specialists), list(tools), [TOOL])


def test_a_good_run_passes_every_check():
    case = Case("r", "How recovered am I?", "health_coach", ("get_recovery",))
    g = grade(case, trace("You're at 8%, red: HRV 49 vs your usual 56."))
    assert g["passed"] and g["checks"]["disclaimer"] is None


def test_each_check_fails_on_its_own():
    case = Case("r", "How recovered am I?", "health_coach", ("get_recovery",))
    assert grade(case, trace("8%.", specialists=("market_scout",)))["checks"]["route"] is False
    assert grade(case, trace("8%.", tools=("get_sleep",)))["checks"]["tools"] is False
    plan = grade(case, trace("8%.", tools=("get_recovery", "adjust_plan")))
    assert plan["checks"]["tools"] is False  # rewrote the plan unasked
    g = grade(case, trace("Recovery is 81%."))
    assert g["checks"]["grounded"] is False and g["ungrounded"] == ["81%"]
    assert grade(case, trace("(no answer)"))["checks"]["answered"] is False


def test_scout_answers_need_the_disclaimer_and_both_routes_work():
    case = Case("s", "Anything up?", "market_scout", ("latest_scan",))
    t = trace("Nothing qualified.", ("market_scout",), ("latest_scan",))
    assert grade(case, t)["checks"]["disclaimer"] is False
    t.answer += "\n\nNot financial advice."
    assert grade(case, t)["passed"]
    both = Case("b", "Both?", "both", tools_all=("get_recovery", "latest_scan"))
    t = Trace(
        "8%. Nothing up. Not financial advice.",
        ["health_coach", "market_scout"],
        ["get_recovery", "latest_scan"],
        [TOOL],
    )
    assert grade(both, t)["passed"]


def test_an_error_fails_the_case():
    g = grade(Case("x", "?", "none"), Trace("", error="APIError: boom"))
    assert not g["passed"] and g["error"] == "APIError: boom"


# False positives from the first real run (2026-11-03): each was the grader's mistake.
SCAN = json.dumps({"coins_under_48h": 1, "volume_h24_usd": "$210k", "strain_0_21": 0.0})


def test_numbers_in_field_names_count_as_evidence():
    assert ungrounded("1 coin under 48 hours, $210k of 24h volume.", [SCAN]) == []
    assert ungrounded("Strain 0.0 out of 21.", [SCAN]) == []


def test_numbers_in_the_agents_instructions_count_as_evidence():
    assert ungrounded("I can show up to 60 days.", [], instructions=["How many days, 1-60."]) == []
    assert ungrounded("Strain runs 0 to 21.", [], instructions=["Strain (0-21) for a day."]) == []


def test_date_ranges_and_years_are_dates():
    assert ungrounded("Yellow from Oct 28 to 31, then 28–31 Oct.", []) == []
    assert ungrounded("Your race is on 14 February 2027.", []) == []


def test_a_trailing_comma_is_not_part_of_the_number():
    assert [n.raw for n in numbers("set 2027, and 1,250 buyers,")] == ["1,250"]
