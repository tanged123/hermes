"""Tests for WebSocket protocol messages."""

from __future__ import annotations

import json

import pytest

from hermes.server.protocol import (
    Command,
    CommandAction,
    EventType,
    ServerMessage,
    ServerMessageType,
    make_ack,
    make_error,
    make_event,
    make_schema,
)


class TestServerMessageType:
    """Tests for ServerMessageType enum."""

    def test_all_types_exist(self) -> None:
        """Should have all required message types."""
        assert ServerMessageType.SCHEMA.value == "schema"
        assert ServerMessageType.EVENT.value == "event"
        assert ServerMessageType.ERROR.value == "error"
        assert ServerMessageType.ACK.value == "ack"

    def test_is_string_enum(self) -> None:
        """Should be a string enum."""
        assert isinstance(ServerMessageType.SCHEMA, str)
        assert ServerMessageType.SCHEMA == "schema"


class TestEventType:
    """Tests for EventType enum."""

    def test_all_events_exist(self) -> None:
        """Should have all state change event types."""
        assert EventType.RUNNING.value == "running"
        assert EventType.PAUSED.value == "paused"
        assert EventType.RESET.value == "reset"
        assert EventType.STOPPED.value == "stopped"


class TestCommandAction:
    """Tests for CommandAction enum."""

    def test_all_actions_exist(self) -> None:
        """Should have all command actions."""
        assert CommandAction.PAUSE.value == "pause"
        assert CommandAction.RESUME.value == "resume"
        assert CommandAction.RESET.value == "reset"
        assert CommandAction.STEP.value == "step"
        assert CommandAction.SET.value == "set"
        assert CommandAction.SUBSCRIBE.value == "subscribe"


class TestServerMessage:
    """Tests for ServerMessage dataclass."""

    def test_create_with_payload(self) -> None:
        """Should create message with payload."""
        msg = ServerMessage(
            type=ServerMessageType.SCHEMA,
            payload={"modules": {"sensor": {}}},
        )
        assert msg.type == ServerMessageType.SCHEMA
        assert msg.payload == {"modules": {"sensor": {}}}

    def test_create_with_default_payload(self) -> None:
        """Should create message with empty default payload."""
        msg = ServerMessage(type=ServerMessageType.ACK)
        assert msg.payload == {}

    def test_to_json(self) -> None:
        """Should serialize to JSON string."""
        msg = ServerMessage(
            type=ServerMessageType.EVENT,
            payload={"event": "running"},
        )
        json_str = msg.to_json()
        parsed = json.loads(json_str)

        assert parsed["type"] == "event"
        assert parsed["event"] == "running"

    def test_to_json_flattens_payload(self) -> None:
        """Should flatten payload into top-level JSON."""
        msg = ServerMessage(
            type=ServerMessageType.ERROR,
            payload={"message": "Something failed", "code": 42},
        )
        json_str = msg.to_json()
        parsed = json.loads(json_str)

        assert parsed["type"] == "error"
        assert parsed["message"] == "Something failed"
        assert parsed["code"] == 42

    def test_to_bytes(self) -> None:
        """Should serialize to UTF-8 bytes."""
        msg = ServerMessage(
            type=ServerMessageType.ACK,
            payload={"action": "pause"},
        )
        data = msg.to_bytes()

        assert isinstance(data, bytes)
        parsed = json.loads(data.decode("utf-8"))
        assert parsed["type"] == "ack"
        assert parsed["action"] == "pause"


class TestCommand:
    """Tests for Command dataclass."""

    def test_create_without_params(self) -> None:
        """Should create command with empty params."""
        cmd = Command(action="pause")
        assert cmd.action == "pause"
        assert cmd.params == {}

    def test_create_with_params(self) -> None:
        """Should create command with params."""
        cmd = Command(action="step", params={"count": 10})
        assert cmd.action == "step"
        assert cmd.params == {"count": 10}

    def test_from_json_simple(self) -> None:
        """Should parse simple command from JSON."""
        data = '{"action": "pause"}'
        cmd = Command.from_json(data)

        assert cmd.action == "pause"
        assert cmd.params == {}

    def test_from_json_with_params(self) -> None:
        """Should parse command with params from JSON."""
        data = '{"action": "step", "params": {"count": 5}}'
        cmd = Command.from_json(data)

        assert cmd.action == "step"
        assert cmd.params == {"count": 5}

    def test_from_json_invalid_json_raises(self) -> None:
        """Should raise ValueError for invalid JSON."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            Command.from_json("not valid json")

    def test_from_json_not_object_raises(self) -> None:
        """Should raise ValueError when JSON is not an object."""
        with pytest.raises(ValueError, match="must be a JSON object"):
            Command.from_json('"just a string"')

    def test_from_json_missing_action_raises(self) -> None:
        """Should raise ValueError when action is missing."""
        with pytest.raises(ValueError, match="missing 'action' field"):
            Command.from_json('{"params": {}}')

    def test_from_json_invalid_params_type_raises(self) -> None:
        """Should raise ValueError when params is not an object."""
        with pytest.raises(ValueError, match="'params' must be an object"):
            Command.from_json('{"action": "pause", "params": "invalid"}')

    def test_validate_known_action(self) -> None:
        """Should validate known action without error."""
        for action in ["pause", "resume", "reset", "step", "set", "subscribe"]:
            cmd = Command(action=action, params={})
            # set and subscribe require params, so skip validation for them
            if action not in ("set", "subscribe"):
                cmd.validate()  # Should not raise

    def test_validate_unknown_action_raises(self) -> None:
        """Should raise ValueError for unknown action."""
        cmd = Command(action="unknown")
        with pytest.raises(ValueError, match="Unknown action: unknown"):
            cmd.validate()

    def test_validate_step_invalid_count(self) -> None:
        """Should raise ValueError for invalid step count."""
        cmd = Command(action="step", params={"count": 0})
        with pytest.raises(ValueError, match="positive integer"):
            cmd.validate()

        cmd = Command(action="step", params={"count": -1})
        with pytest.raises(ValueError, match="positive integer"):
            cmd.validate()

        cmd = Command(action="step", params={"count": "ten"})
        with pytest.raises(ValueError, match="positive integer"):
            cmd.validate()

    def test_validate_step_valid_count(self) -> None:
        """Should validate step with valid count."""
        cmd = Command(action="step", params={"count": 1})
        cmd.validate()  # Should not raise

        cmd = Command(action="step", params={"count": 100})
        cmd.validate()  # Should not raise

    def test_validate_set_missing_signal(self) -> None:
        """Should raise ValueError for set without signal."""
        cmd = Command(action="set", params={"value": 1.0})
        with pytest.raises(ValueError, match="requires 'signal' param"):
            cmd.validate()

    def test_validate_set_missing_value(self) -> None:
        """Should raise ValueError for set without value."""
        cmd = Command(action="set", params={"signal": "test.x"})
        with pytest.raises(ValueError, match="requires 'value' param"):
            cmd.validate()

    def test_validate_set_valid(self) -> None:
        """Should validate set with signal and value."""
        cmd = Command(action="set", params={"signal": "test.x", "value": 42.0})
        cmd.validate()  # Should not raise

    def test_validate_subscribe_missing_signals(self) -> None:
        """Should raise ValueError for subscribe without signals."""
        cmd = Command(action="subscribe", params={})
        with pytest.raises(ValueError, match="requires 'signals' param"):
            cmd.validate()

    def test_validate_subscribe_invalid_signals_type(self) -> None:
        """Should raise ValueError when signals is not a list."""
        cmd = Command(action="subscribe", params={"signals": "test.*"})
        with pytest.raises(ValueError, match="'signals' must be a list"):
            cmd.validate()

    def test_validate_subscribe_valid(self) -> None:
        """Should validate subscribe with signals list."""
        cmd = Command(action="subscribe", params={"signals": ["test.*", "sensor.x"]})
        cmd.validate()  # Should not raise


class TestFactoryFunctions:
    """Tests for message factory functions."""

    def test_make_schema(self) -> None:
        """Should create schema message with modules."""
        modules = {
            "sensor": {
                "signals": [
                    {"name": "temperature", "type": "f64", "unit": "C"},
                ]
            },
            "controller": {
                "signals": [
                    {"name": "command", "type": "f64", "writable": True},
                ]
            },
        }
        msg = make_schema(modules)

        assert msg.type == ServerMessageType.SCHEMA
        assert msg.payload == {"modules": modules}

        # Verify JSON serialization
        parsed = json.loads(msg.to_json())
        assert parsed["type"] == "schema"
        assert "sensor" in parsed["modules"]
        assert "controller" in parsed["modules"]

    def test_make_event_with_enum(self) -> None:
        """Should create event message from EventType enum."""
        msg = make_event(EventType.RUNNING)

        assert msg.type == ServerMessageType.EVENT
        assert msg.payload == {"event": "running"}

    def test_make_event_with_string(self) -> None:
        """Should create event message from string."""
        msg = make_event("paused")

        assert msg.type == ServerMessageType.EVENT
        assert msg.payload == {"event": "paused"}

    def test_make_error_simple(self) -> None:
        """Should create error message with message only."""
        msg = make_error("Something went wrong")

        assert msg.type == ServerMessageType.ERROR
        assert msg.payload == {"message": "Something went wrong"}

    def test_make_error_with_code(self) -> None:
        """Should create error message with code."""
        msg = make_error("Not found", code=404)

        assert msg.type == ServerMessageType.ERROR
        assert msg.payload == {"message": "Not found", "code": 404}

    def test_make_ack_simple(self) -> None:
        """Should create ack message for action."""
        msg = make_ack("pause")

        assert msg.type == ServerMessageType.ACK
        assert msg.payload == {"action": "pause"}

    def test_make_ack_with_details(self) -> None:
        """Should create ack message with details."""
        msg = make_ack("step", {"count": 10, "frame": 42})

        assert msg.type == ServerMessageType.ACK
        assert msg.payload == {"action": "step", "count": 10, "frame": 42}

    def test_make_ack_json_format(self) -> None:
        """Should serialize ack to expected JSON format."""
        msg = make_ack("subscribe", {"count": 5})
        parsed = json.loads(msg.to_json())

        assert parsed["type"] == "ack"
        assert parsed["action"] == "subscribe"
        assert parsed["count"] == 5
