import uuid
from datetime import timedelta

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.core import security as sec
from app.core.db import get_session
from app.core.errors import install_exception_handlers
from tests.conftest import link, make_user


@pytest.fixture
def world(session):
    w = dict(
        admin=make_user(session, "admin"),
        p1=make_user(session, "patient", "P1"),
        p2=make_user(session, "patient", "P2"),
        c1=make_user(session, "caregiver", "C1"),  # linked to p1 only
        c2=make_user(session, "caregiver", "C2"),  # linked to nobody
        hw=make_user(session, "health_worker", "HW"),  # linked to p1 and p2
    )
    link(session, w["c1"], w["p1"])
    link(session, w["hw"], w["p1"], "health_worker")
    link(session, w["hw"], w["p2"], "health_worker")
    return w


MATRIX = [  # (actor, target, allowed)
    ("admin", "p1", True), ("admin", "p2", True),
    ("p1", "p1", True), ("p1", "p2", False), ("p2", "p1", False),
    ("c1", "p1", True), ("c1", "p2", False),
    ("c2", "p1", False), ("c2", "p2", False),
    ("hw", "p1", True), ("hw", "p2", True),
    ("p1", "c1", False), ("c1", "c2", False), ("hw", "admin", False),  # non-patient targets
]


@pytest.mark.parametrize("actor,target,allowed", MATRIX)
def test_access_matrix(session, world, actor, target, allowed):
    user, pid = world[actor], world[target].id
    assert sec.can_access_patient(session, user, pid) is allowed
    if allowed:
        sec.assert_can_access_patient(session, user, pid)
        sec.assert_can_access_patient(session, user, str(pid))  # str ids accepted
    else:
        with pytest.raises(HTTPException) as ei:
            sec.assert_can_access_patient(session, user, pid)
        assert ei.value.status_code == 403


def test_access_unknown_and_malformed_ids(session, world):
    assert sec.can_access_patient(session, world["admin"], uuid.uuid4())  # existence is the route's job (404)
    assert not sec.can_access_patient(session, world["c1"], uuid.uuid4())
    for bad in ("not-a-uuid", "", None):
        with pytest.raises(HTTPException):
            sec.assert_can_access_patient(session, world["admin"], bad)


def test_link_is_directional_and_per_caregiver(session, world):
    # a link for hw must not leak to c1/c2 and vice-versa
    assert sec.accessible_patient_ids(session, world["c1"]) == {world["p1"].id}
    assert sec.accessible_patient_ids(session, world["hw"]) == {world["p1"].id, world["p2"].id}
    assert sec.accessible_patient_ids(session, world["c2"]) == set()
    assert sec.accessible_patient_ids(session, world["p2"]) == {world["p2"].id}
    assert sec.accessible_patient_ids(session, world["admin"]) is None


# ---- HTTP level: get_current_user / require_roles + RFC 7807 --------------------------
@pytest.fixture
def client(session):
    app = FastAPI()
    install_exception_handlers(app)

    @app.get("/whoami")
    def whoami(user=Depends(sec.get_current_user)):
        return {"id": str(user.id), "role": user.role}

    @app.get("/admin-only")
    def admin_only(user=Depends(sec.require_roles("admin"))):
        return {"ok": True}

    @app.get("/staff")
    def staff(user=Depends(sec.require_roles("caregiver", "health_worker"))):
        return {"ok": True}

    @app.get("/patients/{pid}")
    def patient(pid: uuid.UUID, user=Depends(sec.get_current_user), s=Depends(get_session)):
        sec.assert_can_access_patient(s, user, pid)
        return {"patient": str(pid)}

    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app)


def bearer(user, which=0):
    return {"Authorization": f"Bearer {sec.create_tokens(user)[which]}"}


def test_missing_and_bad_credentials_are_401(client, world):
    for headers in ({}, {"Authorization": "Bearer garbage"}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer"}):
        r = client.get("/whoami", headers=headers)
        assert r.status_code == 401, headers
        assert r.headers["www-authenticate"] == "Bearer"
        assert r.headers["content-type"].startswith("application/problem+json")
        body = r.json()
        assert body["status"] == 401 and body["title"] == "Unauthorized" and body["instance"] == "/whoami"


def test_refresh_token_cannot_be_used_as_access(client, world):
    assert client.get("/whoami", headers=bearer(world["c1"], 1)).status_code == 401


def test_expired_access_token(client, world):
    tok = sec.create_token(world["c1"].id, "access", timedelta(seconds=-1))
    assert client.get("/whoami", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_token_for_deleted_user(client, session, world):
    headers = bearer(world["c2"])
    session.delete(world["c2"])
    session.flush()
    assert client.get("/whoami", headers=headers).status_code == 401


def test_valid_token(client, world):
    r = client.get("/whoami", headers=bearer(world["c1"]))
    assert r.status_code == 200 and r.json() == {"id": str(world["c1"].id), "role": "caregiver"}


def test_require_roles(client, world):
    assert client.get("/admin-only", headers=bearer(world["admin"])).status_code == 200
    r = client.get("/admin-only", headers=bearer(world["c1"]))
    assert r.status_code == 403 and r.json()["title"] == "Forbidden"
    assert client.get("/staff", headers=bearer(world["hw"])).status_code == 200
    assert client.get("/staff", headers=bearer(world["p1"])).status_code == 403
    assert client.get("/staff").status_code == 401


def test_patient_route_enforces_rbac(client, world):
    p1, p2 = world["p1"].id, world["p2"].id
    assert client.get(f"/patients/{p1}", headers=bearer(world["c1"])).status_code == 200
    assert client.get(f"/patients/{p2}", headers=bearer(world["c1"])).status_code == 403
    assert client.get(f"/patients/{p1}", headers=bearer(world["p1"])).status_code == 200
    assert client.get(f"/patients/{p1}", headers=bearer(world["p2"])).status_code == 403
    assert client.get(f"/patients/{p2}", headers=bearer(world["admin"])).status_code == 200
    r = client.get("/patients/not-a-uuid", headers=bearer(world["admin"]))
    assert r.status_code == 422 and r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["errors"]
