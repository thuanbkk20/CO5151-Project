import pytest
from pydantic import ValidationError

from co5151_advisor.memory import DecisionTrace, MemoryGate


def test_decision_trace_structure_and_immutability():
    trace = DecisionTrace(action="SUMMARY", sources=["student_mcp"], created_at=1000.0)
    assert trace.action == "SUMMARY"
    assert trace.sources == ["student_mcp"]
    assert trace.created_at == 1000.0

    with pytest.raises(ValidationError):
        DecisionTrace(action="SUMMARY", sources=["student_mcp"], created_at=1000.0, raw_data="forbidden")  # type: ignore[call-arg]


def test_memory_only_permits_goal_and_preference():
    gate = MemoryGate()
    # Allowed kinds
    item1 = gate.store(kind="goal", value="Tốt nghiệp đúng hạn", source="user-stated")
    assert item1.kind == "goal"

    item2 = gate.store(kind="preference", value="Học vào buổi sáng", source="user-stated")
    assert item2.kind == "preference"

    # Disallowed kinds
    with pytest.raises(ValueError, match="Permitted kinds"):
        gate.store(kind="profile", value="Thông tin cá nhân", source="user-stated")

    with pytest.raises(ValueError, match="Permitted kinds"):
        gate.store(kind="academic_history", value="Bảng điểm", source="user-stated")


def test_memory_rejects_mssv():
    gate = MemoryGate()
    with pytest.raises(ValueError, match="seven-digit student ID"):
        gate.store(kind="goal", value="Mục tiêu của MSSV 2310001 là qua môn", source="user-stated")

    with pytest.raises(ValueError, match="seven-digit student ID"):
        gate.store(kind="preference", value="Bạn 2310002 thích học nhóm", source="user-stated")


def test_memory_rejects_token_shaped_strings():
    gate = MemoryGate()
    # Bearer / JWT-like
    with pytest.raises(ValueError, match="token"):
        gate.store(kind="preference", value="Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz", source="user-stated")

    # 32+ hex char hash token
    with pytest.raises(ValueError, match="token"):
        gate.store(kind="preference", value="Token là 5a131b2cd6f84429b94f8bebafce44ca", source="user-stated")


def test_memory_rejects_raw_academic_fields():
    gate = MemoryGate()
    with pytest.raises(ValueError, match="raw academic"):
        gate.store(kind="goal", value="Cần cải thiện diemSo môn này", source="user-stated")

    with pytest.raises(ValueError, match="raw academic"):
        gate.store(kind="preference", value="soCccd 079201000000", source="user-stated")

    with pytest.raises(ValueError, match="raw academic"):
        gate.store(kind="preference", value="session_id=abc123456", source="user-stated")


def test_ttl_expiry():
    gate = MemoryGate()
    base_time = 1000.0
    item = gate.store(kind="preference", value="Học buổi sáng", source="user-stated", ttl=60.0, current_time=base_time)
    assert item.expires_at == 1060.0

    # Within TTL
    items_valid = gate.get_items(current_time=1050.0)
    assert len(items_valid) == 1
    assert items_valid[0].value == "Học buổi sáng"

    # Expired
    items_expired = gate.get_items(current_time=1061.0)
    assert len(items_expired) == 0


def test_user_stated_preference_auto_ingestion():
    gate = MemoryGate()
    statement = "Em ưu tiên học buổi sáng"
    item = gate.process_user_statement(statement)

    assert item is not None
    assert item.kind == "preference"
    assert item.source == "user-stated"
    assert "học buổi sáng" in item.value.lower()

    # Confirms it is now stored in gate
    stored = gate.get_items(kind="preference")
    assert any("buổi sáng" in it.value for it in stored)
