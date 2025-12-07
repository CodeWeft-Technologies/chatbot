import pytest
from app.services.booking import compute_availability

def test_basic_availability_empty_calendar():
    evs = []
    slots = compute_availability("2025-01-01T09:00:00", "2025-01-01T10:00:00", 30, 1, evs)
    assert len(slots) == 2
    assert slots[0]["start"].startswith("2025-01-01T09:00")
    assert slots[1]["start"].startswith("2025-01-01T09:30")

def test_capacity_limits():
    evs = [
        {"start": {"dateTime": "2025-01-01T09:00:00"}},
        {"start": {"dateTime": "2025-01-01T09:00:00"}},
    ]
    slots = compute_availability("2025-01-01T09:00:00", "2025-01-01T10:00:00", 30, 2, evs)
    assert len(slots) == 1
    # capacity 2 with 2 events makes 09:00 full; next is 09:30
    evs2 = evs + [{"start": {"dateTime": "2025-01-01T09:00:00"}}]
    slots2 = compute_availability("2025-01-01T09:00:00", "2025-01-01T10:00:00", 30, 2, evs2)
    assert len(slots2) == 1
    assert slots2[0]["start"].startswith("2025-01-01T09:30")
