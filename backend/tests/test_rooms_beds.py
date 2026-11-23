"""Room and bed management: adding beds, room-wide status, availability rules."""
from main import app
import auth
from conftest import _staff
from test_adt import client, admit  # noqa: F401  (fixtures and helper)


def _room(client, number="201", floor="2"):
    r = client.post("/api/v1/rooms", json={"room_number": number, "floor": floor})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _board_room(client, room_id):
    return next(r for r in client.get("/api/v1/ward-board").json()["rooms"] if r["id"] == room_id)


def test_add_beds_by_count_numbers_them_after_existing(client):
    room = _room(client)
    first = client.post(f"/api/v1/rooms/{room}/beds", json={"count": 3})
    assert first.status_code == 201
    assert [b["bed_number"] for b in first.json()] == ["1", "2", "3"]
    more = client.post(f"/api/v1/rooms/{room}/beds", json={"count": 2}).json()
    assert [b["bed_number"] for b in more] == ["4", "5"]
    assert all(b["status"] == "available" for b in more)


def test_add_beds_by_name_rejects_duplicates_in_same_room_only(client):
    room, other = _room(client, "201"), _room(client, "202")
    assert client.post(f"/api/v1/rooms/{room}/beds", json={"bed_numbers": ["A", " B "]}).status_code == 201
    dup = client.post(f"/api/v1/rooms/{room}/beds", json={"bed_numbers": ["B", "C"]})
    assert dup.status_code == 409 and "already has bed B" in dup.json()["detail"]
    assert [b["bed_number"] for b in _board_room(client, room)["beds"]] == ["A", "B"]   # nothing half-saved
    assert client.post(f"/api/v1/rooms/{other}/beds", json={"bed_numbers": ["A"]}).status_code == 201
    assert client.post("/api/v1/beds", json={"bed_number": "A", "room_id": room}).status_code == 409


def test_add_beds_validates_input(client):
    room = _room(client)
    assert client.post(f"/api/v1/rooms/{room}/beds", json={}).status_code == 422
    assert client.post(f"/api/v1/rooms/{room}/beds", json={"bed_numbers": ["  "]}).status_code == 422
    assert client.post(f"/api/v1/rooms/{room}/beds", json={"count": 0}).status_code == 422
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.post(f"/api/v1/rooms/{missing}/beds", json={"count": 1}).status_code == 404


def test_only_admin_adds_beds_or_marks_rooms(client):
    room = _room(client)
    app.dependency_overrides[auth.current_user] = lambda: _staff("doctor")
    assert client.post(f"/api/v1/rooms/{room}/beds", json={"count": 1}).status_code == 403
    assert client.patch(f"/api/v1/rooms/{room}/status", json={"status": "cleaning"}).status_code == 403


def test_room_status_skips_occupied_beds_and_summary_counts(client):
    doctor = client.post("/api/v1/doctors", json={"name": "Dr. Demo"}).json()["id"]
    room = _room(client)
    beds = [b["id"] for b in client.post(f"/api/v1/rooms/{room}/beds", json={"count": 3}).json()]
    admit(client, {"doctor": doctor, "room": room, "beds": beds}, bed=0)

    r = client.patch(f"/api/v1/rooms/{room}/status", json={"status": "maintenance"})
    assert r.status_code == 200
    assert r.json()["changed"] == ["2", "3"] and r.json()["skipped_occupied"] == ["1"]
    assert _board_room(client, room)["summary"] == {"occupied": 1, "available": 0, "cleaning": 0, "maintenance": 2}

    client.patch(f"/api/v1/rooms/{room}/status", json={"status": "available"})
    assert _board_room(client, room)["summary"] == {"occupied": 1, "available": 2, "cleaning": 0, "maintenance": 0}
    assert client.patch(f"/api/v1/rooms/{room}/status", json={"status": "occupied"}).status_code == 422


def test_cannot_admit_to_occupied_cleaning_or_maintenance_bed(client):
    doctor = client.post("/api/v1/doctors", json={"name": "Dr. Demo"}).json()["id"]
    room = _room(client)
    beds = [b["id"] for b in client.post(f"/api/v1/rooms/{room}/beds", json={"count": 3}).json()]
    ward = {"doctor": doctor, "room": room, "beds": beds}
    admit(client, ward, bed=0)
    client.patch(f"/api/v1/beds/{beds[1]}/status", json={"status": "cleaning"})
    client.patch(f"/api/v1/beds/{beds[2]}/status", json={"status": "maintenance"})
    for i in range(3):
        r = client.post("/api/v1/patients", json={"name": "Second Patient", "age": 60, "condition": "Obs",
                                                  "doctor_id": doctor, "room_id": room, "bed_id": beds[i]})
        assert r.status_code == 409, (i, r.text)
