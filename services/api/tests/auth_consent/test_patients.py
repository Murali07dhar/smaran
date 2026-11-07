from __future__ import annotations


def test_create_patient_auto_links_creating_caregiver(client, make_caregiver, auth_headers):
    caregiver, _ = make_caregiver()
    headers, _ = auth_headers(caregiver)

    resp = client.post(
        "/api/v1/patients", json={"name": "Grandma Devi", "age": 72, "language": "as"}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    patient_id = resp.json()["id"]
    assert resp.json()["open_alerts"] == 0
    assert resp.json()["last_active_at"] is None

    listing = client.get("/api/v1/patients", headers=headers)
    assert listing.status_code == 200
    assert any(p["id"] == patient_id for p in listing.json())


def test_patient_role_cannot_create_patient(client, make_patient, auth_headers):
    patient = make_patient()
    headers, _ = auth_headers(patient)
    resp = client.post(
        "/api/v1/patients", json={"name": "Someone", "age": 65, "language": "en"}, headers=headers
    )
    assert resp.status_code == 403


def test_caregiver_sees_only_linked_patients(client, make_caregiver, make_patient, auth_headers):
    caregiver_a, _ = make_caregiver(email="a@example.com")
    caregiver_b, _ = make_caregiver(email="b@example.com")
    patient_a = make_patient(name="Patient A", caregiver=caregiver_a)
    make_patient(name="Patient B", caregiver=caregiver_b)

    headers_a, _ = auth_headers(caregiver_a)
    resp = client.get("/api/v1/patients", headers=headers_a)
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()]
    assert str(patient_a.id) in ids
    assert len(ids) == 1


def test_health_worker_sees_all_patients(client, make_health_worker, make_caregiver, make_patient, auth_headers):
    caregiver, _ = make_caregiver()
    make_patient(name="P1", caregiver=caregiver)
    make_patient(name="P2", caregiver=caregiver)
    hw, _ = make_health_worker()

    headers, _ = auth_headers(hw)
    resp = client.get("/api/v1/patients", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_unlinked_caregiver_cannot_read_patient(client, make_caregiver, make_patient, auth_headers):
    owner, _ = make_caregiver(email="owner@example.com")
    stranger, _ = make_caregiver(email="stranger@example.com")
    patient = make_patient(caregiver=owner)

    headers, _ = auth_headers(stranger)
    resp = client.get(f"/api/v1/patients/{patient.id}", headers=headers)
    assert resp.status_code == 403


def test_linked_caregiver_can_read_patient(client, make_caregiver, make_patient, auth_headers):
    owner, _ = make_caregiver()
    patient = make_patient(caregiver=owner)
    headers, _ = auth_headers(owner)
    resp = client.get(f"/api/v1/patients/{patient.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == str(patient.id)


def test_add_second_caregiver_link(client, make_caregiver, make_patient, auth_headers):
    owner, _ = make_caregiver(email="owner2@example.com")
    family_member, _ = make_caregiver(email="family@example.com")
    patient = make_patient(caregiver=owner)

    headers, _ = auth_headers(owner)
    resp = client.post(
        "/api/v1/caregiver-links",
        json={"caregiver_id": str(family_member.id), "patient_id": str(patient.id), "relation": "son"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text

    family_headers, _ = auth_headers(family_member)
    now_visible = client.get(f"/api/v1/patients/{patient.id}", headers=family_headers)
    assert now_visible.status_code == 200


def test_stranger_cannot_add_caregiver_link(client, make_caregiver, make_patient, auth_headers):
    owner, _ = make_caregiver(email="owner3@example.com")
    stranger, _ = make_caregiver(email="stranger3@example.com")
    outsider, _ = make_caregiver(email="outsider3@example.com")
    patient = make_patient(caregiver=owner)

    headers, _ = auth_headers(stranger)
    resp = client.post(
        "/api/v1/caregiver-links",
        json={"caregiver_id": str(outsider.id), "patient_id": str(patient.id), "relation": "friend"},
        headers=headers,
    )
    assert resp.status_code == 403
