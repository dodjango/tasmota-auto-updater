"""Unit tests for the thin CLI wrapper (app/cli.py)."""
import pytest

from app import cli


def test_parser_requires_a_command():
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


@pytest.mark.parametrize("command", ["check", "update", "list"])
def test_parser_accepts_each_command(command):
    args = cli.build_parser().parse_args([command])
    assert args.command == command
    assert args.file is None
    assert args.json is False
    assert args.log_level == "WARNING"


def test_parser_accepts_update_options():
    args = cli.build_parser().parse_args(["update", "--timeout", "300", "--force"])
    assert args.timeout == 300
    assert args.force is True


@pytest.mark.parametrize("command", ["check", "list"])
def test_parser_rejects_update_options_on_other_commands(command):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([command, "--force"])


def test_resolve_devices_file_prefers_explicit_path():
    assert cli.resolve_devices_file("custom.yaml", {"DEVICES_FILE": "env.yaml"}) == "custom.yaml"


def test_resolve_devices_file_falls_back_to_environment():
    assert cli.resolve_devices_file(None, {"DEVICES_FILE": "env.yaml"}) == "env.yaml"


def test_resolve_devices_file_defaults_to_devices_yaml():
    assert cli.resolve_devices_file(None, {}) == "devices.yaml"
