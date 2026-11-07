import pickle

from app.core.difficulty import new_events

GOOD = {"correct": True, "response_ms": 2000, "hints": 0}
TIRING = {"correct": False, "response_ms": 5000, "hints": 2}


def call(client, recent, current=4, pid="p1", game="g1"):
    r = client.post("/ai/difficulty/next", json={"patient_id": pid, "game_id": game, "recent": recent,
                                                 "current_difficulty": current})
    assert r.status_code == 200, r.text
    return r.json()


def test_goes_up_when_smooth(client):
    r = call(client, [GOOD] * 6)
    assert r["difficulty"] == 5
    assert "more challenging" in r["rationale"]


def test_goes_down_when_tiring(client):
    r = call(client, [TIRING] * 6)
    assert r["difficulty"] <= 3
    assert "gentler" in r["rationale"]


def test_holds_in_comfortable_range(client):
    window = [GOOD, GOOD, GOOD, {**GOOD, "correct": False}, GOOD, {**GOOD, "correct": False}]
    assert call(client, window)["difficulty"] == 4


def test_holds_with_too_little_data(client):
    r = call(client, [GOOD, GOOD])
    assert r["difficulty"] == 4
    assert "only 2" in r["rationale"]


def test_bounds_respected(client):
    assert call(client, [GOOD] * 6, current=10, pid="top")["difficulty"] == 10
    assert call(client, [TIRING] * 6, current=1, pid="bottom")["difficulty"] == 1


def test_rationale_has_no_failure_language(client):
    for window in ([GOOD] * 6, [TIRING] * 6, [GOOD, TIRING] * 3):
        text = call(client, window, pid=str(len(window)) + str(window[0]))["rationale"].lower()
        assert not any(w in text for w in ("fail", "wrong", "incorrect", "mistake", "penalty", "score"))


def test_overlap_trim_unit():
    a, b, c, d = (True, 1, 0), (False, 2, 0), (True, 3, 0), (True, 4, 0)
    assert new_events([a, b, c], [b, c, d]) == [d]
    assert new_events([a, b, c], [a, b, c]) == []
    assert new_events([], [a, b]) == [a, b]
    assert new_events([a], [b, c]) == [b, c]


def test_resent_window_is_not_double_counted(client):
    window = [GOOD] * 6
    call(client, window)
    call(client, window)
    model = pickle.loads(client.app.state.store.load_blob("diff:p1:g1"))  # noqa: S301
    assert model.n == 6


def test_state_is_per_game(client):
    call(client, [GOOD] * 6, game="a")
    call(client, [GOOD] * 6, game="b")
    store = client.app.state.store
    assert store.load_blob("diff:p1:a") and store.load_blob("diff:p1:b")


def test_validation(client):
    r = client.post("/ai/difficulty/next", json={"patient_id": "p", "game_id": "g", "recent": [],
                                                 "current_difficulty": 11})
    assert r.status_code == 422
