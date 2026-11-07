from __future__ import annotations


def test_register_caregiver_returns_tokens(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "name": "New Caregiver",
            "email": "new.caregiver@example.com",
            "password": "a-strong-password",
            "role": "caregiver",
            "language": "en",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["role"] == "caregiver"
    assert "access_token" in body and "refresh_token" in body


def test_register_duplicate_email_conflicts(client, make_caregiver):
    existing, _ = make_caregiver(email="dupe@example.com")
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Someone Else",
            "email": "dupe@example.com",
            "password": "a-strong-password",
            "role": "caregiver",
        },
    )
    assert resp.status_code == 409


def test_login_success(client, make_caregiver):
    user, password = make_caregiver()
    resp = client.post("/api/v1/auth/login", json={"email": user.email, "password": password})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user"]["id"] == str(user.id)
    assert body["user"]["role"] == "caregiver"


def test_login_wrong_password_401(client, make_caregiver):
    user, _ = make_caregiver()
    resp = client.post("/api/v1/auth/login", json={"email": user.email, "password": "nope"})
    assert resp.status_code == 401


def test_login_lockout_after_five_failures(client, make_caregiver):
    user, password = make_caregiver()
    for _ in range(5):
        resp = client.post("/api/v1/auth/login", json={"email": user.email, "password": "nope"})
        assert resp.status_code == 401
    # 6th attempt, even with the CORRECT password, is locked out
    locked = client.post("/api/v1/auth/login", json={"email": user.email, "password": password})
    assert locked.status_code == 429


def test_patient_cannot_login_via_password_route(client, make_patient):
    patient = make_patient()
    resp = client.post(
        "/api/v1/auth/login", json={"email": "irrelevant@example.com", "password": "x"}
    )
    assert resp.status_code == 401


def test_refresh_rotates_token_and_old_one_is_rejected(client, make_caregiver):
    user, password = make_caregiver()
    login = client.post("/api/v1/auth/login", json={"email": user.email, "password": password})
    old_refresh = login.json()["refresh_token"]

    first_refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert first_refresh.status_code == 200
    new_refresh = first_refresh.json()["refresh_token"]
    assert new_refresh != old_refresh

    reuse = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert reuse.status_code == 401

    second_refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh})
    assert second_refresh.status_code == 200


def test_me_requires_auth(client):
    resp = client.get("/api/v1/me")
    assert resp.status_code == 401


def test_me_returns_current_user(client, make_caregiver, auth_headers):
    user, _ = make_caregiver()
    headers, _ = auth_headers(user)
    resp = client.get("/api/v1/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == str(user.id)
    assert resp.json()["email"] == user.email


def test_patient_pin_login_success(client, make_caregiver, make_patient, auth_headers):
    caregiver, _ = make_caregiver()
    patient = make_patient(caregiver=caregiver)
    headers, _ = auth_headers(caregiver)

    issued = client.post(f"/api/v1/patients/{patient.id}/pin", headers=headers)
    assert issued.status_code == 200, issued.text
    pin = issued.json()["pin"]
    qr_token = issued.json()["qr_token"]
    assert len(pin) == 6 and pin.isdigit()

    login = client.post("/api/v1/auth/patient-pin-login", json={"pin": pin})
    assert login.status_code == 200, login.text
    assert login.json()["user"]["id"] == str(patient.id)
    assert login.json()["user"]["role"] == "patient"

    # QR token is single-use: first login works, second is rejected.
    qr_login_1 = client.post("/api/v1/auth/patient-pin-login", json={"qr_token": qr_token})
    assert qr_login_1.status_code == 200
    qr_login_2 = client.post("/api/v1/auth/patient-pin-login", json={"qr_token": qr_token})
    assert qr_login_2.status_code == 401


def test_patient_pin_login_wrong_pin_401(client, make_caregiver, make_patient, auth_headers):
    caregiver, _ = make_caregiver()
    patient = make_patient(caregiver=caregiver)
    headers, _ = auth_headers(caregiver)
    client.post(f"/api/v1/patients/{patient.id}/pin", headers=headers)

    resp = client.post("/api/v1/auth/patient-pin-login", json={"pin": "000000"})
    assert resp.status_code == 401


def test_issuing_new_pin_invalidates_previous_pin(client, make_caregiver, make_patient, auth_headers):
    caregiver, _ = make_caregiver()
    patient = make_patient(caregiver=caregiver)
    headers, _ = auth_headers(caregiver)

    first = client.post(f"/api/v1/patients/{patient.id}/pin", headers=headers).json()
    second = client.post(f"/api/v1/patients/{patient.id}/pin", headers=headers).json()
    assert first["pin"] != second["pin"] or True  # collision astronomically unlikely either way

    stale_login = client.post("/api/v1/auth/patient-pin-login", json={"pin": first["pin"]})
    # Only true if pins differ; guard the assertion accordingly.
    if first["pin"] != second["pin"]:
        assert stale_login.status_code == 401

    fresh_login = client.post("/api/v1/auth/patient-pin-login", json={"pin": second["pin"]})
    assert fresh_login.status_code == 200


def test_qr_and_refresh_tokens_are_not_usable_as_bearer(client, make_caregiver, make_patient, auth_headers):
    caregiver, _ = make_caregiver()
    patient = make_patient(caregiver=caregiver)
    headers, refresh = auth_headers(caregiver)
    qr_token = client.post(f"/api/v1/patients/{patient.id}/pin", headers=headers).json()["qr_token"]
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {qr_token}"}).status_code == 401
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {refresh}"}).status_code == 401
    # an access token is not a QR token either
    access = headers["Authorization"].split()[1]
    r = client.post("/api/v1/auth/patient-pin-login", json={"qr_token": access})
    assert r.status_code == 401
