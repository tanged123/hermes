"""Tests for IPC message formats."""

from __future__ import annotations

import json

import pytest

from hermes.protocol.messages import Command, ControlMessage, MessageType


class TestMessageType:
    """Tests for MessageType enum."""

    def test_lifecycle_commands(self) -> None:
        """Should have all lifecycle command types."""
        assert MessageType.STAGE.value == "stage"
        assert MessageType.RESET.value == "reset"
        assert MessageType.TERMINATE.value == "terminate"

    def test_runtime_commands(self) -> None:
        """Should have all runtime command types."""
        assert MessageType.STEP.value == "step"
        assert MessageType.PAUSE.value == "pause"
        assert MessageType.RESUME.value == "resume"

    def test_response_types(self) -> None:
        """Should have all response types."""
        assert MessageType.ACK.value == "ack"
        assert MessageType.ERROR.value == "error"
        assert MessageType.READY.value == "ready"

    def test_string_enum(self) -> None:
        """MessageType should be string enum."""
        assert isinstance(MessageType.STAGE, str)
        assert MessageType.STAGE == "stage"


class TestControlMessage:
    """Tests for ControlMessage dataclass."""

    def test_create_without_payload(self) -> None:
        """Should create message without payload."""
        msg = ControlMessage(type=MessageType.STEP)
        assert msg.type == MessageType.STEP
        assert msg.payload is None

    def test_create_with_payload(self) -> None:
        """Should create message with payload."""
        msg = ControlMessage(
            type=MessageType.ERROR,
            payload={"error": "Something went wrong"},
        )
        assert msg.type == MessageType.ERROR
        assert msg.payload == {"error": "Something went wrong"}

    def test_to_bytes_without_payload(self) -> None:
        """Should serialize to bytes without payload."""
        msg = ControlMessage(type=MessageType.STEP)
        data = msg.to_bytes()

        assert data.endswith(b"\n")
        parsed = json.loads(data.decode("utf-8"))
        assert parsed["type"] == "step"
        assert "payload" not in parsed

    def test_to_bytes_with_payload(self) -> None:
        """Should serialize to bytes with payload."""
        msg = ControlMessage(
            type=MessageType.ERROR,
            payload={"message": "test error", "code": 42},
        )
        data = msg.to_bytes()

        assert data.endswith(b"\n")
        parsed = json.loads(data.decode("utf-8"))
        assert parsed["type"] == "error"
        assert parsed["payload"]["message"] == "test error"
        assert parsed["payload"]["code"] == 42

    def test_from_bytes_without_payload(self) -> None:
        """Should deserialize from bytes without payload."""
        data = b'{"type": "stage"}\n'
        msg = ControlMessage.from_bytes(data)

        assert msg.type == MessageType.STAGE
        assert msg.payload is None

    def test_from_bytes_with_payload(self) -> None:
        """Should deserialize from bytes with payload."""
        data = b'{"type": "error", "payload": {"message": "failed"}}\n'
        msg = ControlMessage.from_bytes(data)

        assert msg.type == MessageType.ERROR
        assert msg.payload == {"message": "failed"}

    def test_from_bytes_without_newline(self) -> None:
        """Should handle data without trailing newline."""
        data = b'{"type": "ack"}'
        msg = ControlMessage.from_bytes(data)

        assert msg.type == MessageType.ACK

    def test_from_bytes_with_whitespace(self) -> None:
        """Should handle whitespace in data."""
        data = b'  {"type": "ready"}  \n'
        msg = ControlMessage.from_bytes(data)

        assert msg.type == MessageType.READY

    def test_from_bytes_invalid_json_raises(self) -> None:
        """Should raise ValueError for invalid JSON."""
        data = b"not valid json"
        with pytest.raises(ValueError, match="Invalid message format"):
            ControlMessage.from_bytes(data)

    def test_from_bytes_invalid_type_raises(self) -> None:
        """Should raise ValueError for invalid message type."""
        data = b'{"type": "invalid_type"}\n'
        with pytest.raises(ValueError):
            ControlMessage.from_bytes(data)

    def test_roundtrip(self) -> None:
        """Should survive serialization roundtrip."""
        original = ControlMessage(
            type=MessageType.STEP,
            payload={"frame": 42, "time": 1.5},
        )
        data = original.to_bytes()
        restored = ControlMessage.from_bytes(data)

        assert restored.type == original.type
        assert restored.payload == original.payload


class TestCommand:
    """Tests for Command dataclass."""

    def test_create_without_params(self) -> None:
        """Should create command without params."""
        cmd = Command(action="step")
        assert cmd.action == "step"
        assert cmd.params is None

    def test_create_with_params(self) -> None:
        """Should create command with params."""
        cmd = Command(action="stage", params={"config": "/path/to/config"})
        assert cmd.action == "stage"
        assert cmd.params == {"config": "/path/to/config"}

    def test_to_message_known_action(self) -> None:
        """Should convert known action to ControlMessage."""
        cmd = Command(action="step", params={"frame": 1})
        msg = cmd.to_message()

        assert msg.type == MessageType.STEP
        assert msg.payload == {"frame": 1}

    def test_to_message_known_action_no_params(self) -> None:
        """Should convert known action without params."""
        cmd = Command(action="pause")
        msg = cmd.to_message()

        assert msg.type == MessageType.PAUSE
        assert msg.payload is None

    def test_to_message_unknown_action_raises(self) -> None:
        """Should raise ValueError for unknown action."""
        cmd = Command(action="custom_action", params={"key": "value"})

        with pytest.raises(ValueError, match="Unknown action: custom_action"):
            cmd.to_message()

    def test_to_message_unknown_action_no_params_raises(self) -> None:
        """Should raise ValueError for unknown action without params."""
        cmd = Command(action="unknown")

        with pytest.raises(ValueError, match="Unknown action: unknown"):
            cmd.to_message()

    def test_all_message_types_convertible(self) -> None:
        """Should convert all standard message types."""
        for msg_type in MessageType:
            cmd = Command(action=msg_type.value)
            msg = cmd.to_message()
            assert msg.type == msg_type
