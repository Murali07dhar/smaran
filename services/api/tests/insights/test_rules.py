from datetime import timedelta

from app.modules.insights import rules
from app.modules.insights.rules import ReminderHistory
from insights_helpers import NOW


def test_score_drop_threshold_is_strictly_more_than_20_percent():
    assert rules.evaluate_score_drop(80, 100, 3, 3) is None          # exactly 20%
    d = rules.evaluate_score_drop(79, 100, 3, 3)                     # 21%
    assert d and d.kind == "score_drop" and d.severity == "watch"


def test_score_drop_escalates_to_alert_at_40_percent():
    assert rules.evaluate_score_drop(60, 100, 3, 3).severity == "alert"
    assert rules.evaluate_score_drop(61, 100, 3, 3).severity == "watch"


def test_score_drop_needs_both_windows_and_positive_baseline():
    assert rules.evaluate_score_drop(None, 100, 0, 3) is None
    assert rules.evaluate_score_drop(50, None, 3, 0) is None
    assert rules.evaluate_score_drop(50, 0, 3, 3) is None
    assert rules.evaluate_score_drop(120, 100, 3, 3) is None         # improvement


def test_score_drop_message_has_no_failure_language_and_carries_disclaimer():
    m = rules.evaluate_score_drop(50, 100, 3, 3).message.lower()
    assert "not a diagnosis" in m
    assert "fail" not in m


def test_activity_drop_boundaries():
    assert rules.evaluate_activity_drop(None, NOW) is None
    assert rules.evaluate_activity_drop(NOW - timedelta(days=2, hours=23), NOW) is None
    d = rules.evaluate_activity_drop(NOW - timedelta(days=3), NOW)
    assert d and d.severity == "watch"
    assert rules.evaluate_activity_drop(NOW - timedelta(days=7), NOW).severity == "alert"


def _h(statuses, escalate=3, category="medicine", title="T"):
    return ReminderHistory("r", title, category, escalate, tuple(statuses))


def test_missed_reminders_streak_rules():
    assert rules.evaluate_missed_reminders([_h(["missed", "missed"])]) is None
    d = rules.evaluate_missed_reminders([_h(["missed"] * 3)])
    assert d and d.kind == "missed_reminders"
    assert rules.evaluate_missed_reminders([_h(["missed", "done", "missed", "missed"])]) is None
    assert rules.evaluate_missed_reminders([_h(["later", "missed", "missed", "missed"])]) is None


def test_missed_reminders_ignores_disabled_escalation_and_sets_severity():
    assert rules.evaluate_missed_reminders([_h(["missed"] * 5, escalate=0)]) is None
    assert rules.evaluate_missed_reminders([_h(["missed"] * 3, category="hydration")]).severity == "watch"
    assert rules.evaluate_missed_reminders([_h(["missed"] * 3, category="medicine")]).severity == "alert"


def test_missed_reminders_multiple_reminders_one_decision():
    d = rules.evaluate_missed_reminders([_h(["missed"] * 3, title="A"), _h(["missed"] * 3, title="B")])
    assert "2 reminders" in d.message


def test_severity_band_decisions():
    assert rules.evaluate_severity_band("stable", 2) is None
    assert rules.evaluate_severity_band("watch", 4).severity == "watch"
    assert rules.evaluate_severity_band("alert", 6).severity == "alert"


def test_should_escalate():
    assert rules.should_escalate("watch", "alert")
    assert not rules.should_escalate("alert", "watch")
    assert not rules.should_escalate("watch", "watch")
