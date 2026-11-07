from __future__ import annotations


def test_post_and_get_consent_history(client, make_caregiver, make_patient, auth_headers):
    caregiver, _ = make_caregiver()
    patient = make_patient(caregiver=caregiver)
    headers, _ = auth_headers(caregiver)

    grant = client.post(
        f"/api/v1/patients/{patient.id}/consents",
        json={"kind": "camera", "granted": True},
        headers=headers,
    )
    assert grant.status_code == 201, grant.text
    assert grant.json()["granted_by"] == str(caregiver.id)

    revoke = client.post(
        f"/api/v1/patients/{patient.id}/consents",
        json={"kind": "camera", "granted": False},
        headers=headers,
    )
    assert revoke.status_code == 201

    listing = client.get(f"/api/v1/patients/{patient.id}/consents", headers=headers)
    assert listing.status_code == 200
    body = listing.json()
    assert body["latest"]["camera"]["granted"] is False
    assert len(body["history"]) == 2


def test_consents_require_patient_access(client, make_caregiver, make_patient, auth_headers):
    owner, _ = make_caregiver(email="owner4@example.com")
    stranger, _ = make_caregiver(email="stranger4@example.com")
    patient = make_patient(caregiver=owner)

    headers, _ = auth_headers(stranger)
    resp = client.get(f"/api/v1/patients/{patient.id}/consents", headers=headers)
    assert resp.status_code == 403


def test_multiple_kinds_tracked_independently(client, make_caregiver, make_patient, auth_headers):
    caregiver, _ = make_caregiver()
    patient = make_patient(caregiver=caregiver)
    headers, _ = auth_headers(caregiver)

    for kind in ("camera", "mic", "data_sharing"):
        resp = client.post(
            f"/api/v1/patients/{patient.id}/consents",
            json={"kind": kind, "granted": True},
            headers=headers,
        )
        assert resp.status_code == 201

    listing = client.get(f"/api/v1/patients/{patient.id}/consents", headers=headers)
    latest = listing.json()["latest"]
    assert set(latest.keys()) == {"camera", "mic", "data_sharing"}
    assert all(v["granted"] for v in latest.values())
