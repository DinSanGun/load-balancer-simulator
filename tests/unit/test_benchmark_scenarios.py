from __future__ import annotations

import pytest

from app.benchmark_scenarios import get_scenario, list_scenario_names, scenario_backend_behaviors_dict


def test_list_scenario_names_is_sorted_and_nonempty() -> None:
    names = list_scenario_names()
    assert names == sorted(names)
    assert "balanced" in names
    assert "one_slow_backend" in names
    assert "flaky_backend" in names
    assert "high_jitter" in names


def test_get_scenario_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown scenario"):
        get_scenario("no_such_scenario")


def test_scenario_backend_behaviors_serializable() -> None:
    sc = get_scenario("balanced")
    d = scenario_backend_behaviors_dict(sc)
    assert set(d.keys()) == {"backend-1", "backend-2", "backend-3"}
    assert d["backend-1"]["fixed_delay_ms"] == 100
    assert d["backend-1"]["failure_rate"] == 0.0
