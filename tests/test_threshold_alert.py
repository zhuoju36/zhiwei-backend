"""阈值告警评估单元测试。"""

from app.services.alert_service import evaluate_thresholds


def test_empty_rules_returns_empty() -> None:
    assert evaluate_thresholds(1.0, None) == []
    assert evaluate_thresholds(1.0, []) == []


def test_gt_triggers_when_value_exceeds() -> None:
    rules = [{"operator": "gt", "threshold": 0.5, "level": "warning"}]
    assert len(evaluate_thresholds(0.51, rules)) == 1
    assert evaluate_thresholds(0.5, rules) == []  # 边界不触发
    assert evaluate_thresholds(0.49, rules) == []


def test_lt_triggers_when_value_below() -> None:
    rules = [{"operator": "lt", "threshold": 0.0, "level": "danger"}]
    assert len(evaluate_thresholds(-0.01, rules)) == 1
    assert evaluate_thresholds(0.0, rules) == []


def test_all_operators() -> None:
    rules = [
        {"operator": "gt", "threshold": 10, "level": "info"},
        {"operator": "lt", "threshold": -10, "level": "info"},
        {"operator": "ge", "threshold": 0, "level": "info"},
        {"operator": "le", "threshold": 0, "level": "info"},
        {"operator": "eq", "threshold": 5, "level": "info"},
        {"operator": "ne", "threshold": 5, "level": "info"},
    ]
    events = evaluate_thresholds(0, rules)
    assert len(events) == 3  # ge=0, le=0, ne=5
    assert all(e.level == "info" for e in events)


def test_multiple_levels_independent() -> None:
    rules = [
        {"operator": "gt", "threshold": 0.3, "level": "warning"},
        {"operator": "gt", "threshold": 0.6, "level": "danger"},
    ]
    events = evaluate_thresholds(0.4, rules)
    levels = [e.level for e in events]
    assert levels == ["warning"]

    events = evaluate_thresholds(0.7, rules)
    levels = sorted(e.level for e in events)
    assert levels == ["danger", "warning"]


def test_invalid_rule_skipped() -> None:
    rules = [
        {"operator": "invalid", "threshold": 1, "level": "info"},
        {"threshold": 1, "level": "info"},  # missing operator
        {"operator": "gt", "level": "info"},  # missing threshold
    ]
    assert evaluate_thresholds(2.0, rules) == []


def test_message_preserved() -> None:
    rules = [{"operator": "gt", "threshold": 1.0, "level": "warning", "message": "超限"}]
    events = evaluate_thresholds(2.0, rules)
    assert events[0].message == "超限"
