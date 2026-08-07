"""Unit tests for the thin CLI wrapper (app/cli.py)."""
import json
import re

import pytest

from app import cli


def test_parser_requires_a_command():
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


@pytest.mark.parametrize("command", ["check", "update", "list"])
def test_parser_accepts_each_command(command):
    args = cli.build_parser().parse_args([command, "--json"])
    assert args.command == command
    assert args.json is True
    assert args.file is None
    assert args.log_level == "WARNING"


def test_parser_accepts_update_options():
    args = cli.build_parser().parse_args(["update", "--timeout", "300", "--force"])
    assert args.timeout == 300
    assert args.force is True


def test_parser_accepts_shared_options_after_verb():
    args = cli.build_parser().parse_args(["check", "-f", "custom.yaml", "--log-level", "DEBUG"])
    assert args.file == "custom.yaml"
    assert args.log_level == "DEBUG"


def test_parser_rejects_shared_options_before_verb():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--json", "check"])


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


def _result(**overrides):
    base = {
        "ip": "192.168.8.191",
        "success": True,
        "current_version": "14.6.0",
        "latest_version": "15.0.1",
        "needs_update": False,
    }
    base.update(overrides)
    return base


def test_classify_failed_device():
    assert cli.classify(_result(success=False)) == "failed"


@pytest.mark.parametrize("latest", ["Unknown", "", None])
def test_classify_unknown_comparison(latest):
    assert cli.classify(_result(latest_version=latest)) == "comparison_unknown"


def test_classify_missing_latest_version_is_unknown():
    result = _result()
    del result["latest_version"]
    assert cli.classify(result) == "comparison_unknown"


def test_classify_needs_update():
    assert cli.classify(_result(needs_update=True)) == "needs_update"


def test_classify_up_to_date():
    assert cli.classify(_result()) == "up_to_date"


def test_classify_failure_wins_over_unknown():
    assert cli.classify(_result(success=False, latest_version="Unknown")) == "failed"


def test_summarize_check_counts_every_class():
    results = [
        _result(ip="1", needs_update=True),
        _result(ip="2"),
        _result(ip="3", latest_version="Unknown"),
        _result(ip="4", success=False),
    ]
    assert cli.summarize(results, "check") == {
        "total": 4,
        "up_to_date": 1,
        "needs_update": 1,
        "comparison_unknown": 1,
        "failed": 1,
    }


def test_summarize_list_only_counts_failures():
    results = [_result(ip="1"), _result(ip="2", success=False)]
    assert cli.summarize(results, "list") == {"total": 2, "failed": 1}


def test_summarize_update_counts_updated_and_skipped():
    results = [
        _result(ip="1", needs_update=True, update_completed=True),
        _result(ip="2"),
        _result(ip="3", success=False, update_started=True),
        _result(ip="4", latest_version="Unknown"),
    ]
    assert cli.summarize(results, "update") == {
        "total": 4,
        "updated": 1,
        "skipped": 1,
        "comparison_unknown": 1,
        "failed": 1,
    }


def test_summarize_update_does_not_count_an_updated_device_as_skipped():
    """After a successful update the device reports the new version, so it
    classifies as up_to_date — it must not land in both buckets."""
    results = [_result(ip="1", needs_update=False, update_completed=True)]
    assert cli.summarize(results, "update") == {
        "total": 1,
        "updated": 1,
        "skipped": 0,
        "comparison_unknown": 0,
        "failed": 0,
    }


def test_exit_code_ok_when_everything_current():
    summary = cli.summarize([_result()], "check")
    assert cli.exit_code_for("check", summary) == cli.EXIT_OK


def test_exit_code_outdated_for_check():
    summary = cli.summarize([_result(needs_update=True)], "check")
    assert cli.exit_code_for("check", summary) == cli.EXIT_OUTDATED


def test_exit_code_error_on_unknown_comparison():
    summary = cli.summarize([_result(latest_version="Unknown")], "check")
    assert cli.exit_code_for("check", summary) == cli.EXIT_ERROR


def test_exit_code_error_beats_outdated():
    results = [_result(ip="1", needs_update=True), _result(ip="2", success=False)]
    summary = cli.summarize(results, "check")
    assert cli.exit_code_for("check", summary) == cli.EXIT_ERROR


def test_exit_code_update_never_returns_one():
    """A device that was just updated still carries needs_update from before."""
    results = [_result(needs_update=True, update_completed=True)]
    summary = cli.summarize(results, "update")
    assert cli.exit_code_for("update", summary) == cli.EXIT_OK


def test_exit_code_update_reports_failure():
    results = [_result(success=False, update_started=True)]
    summary = cli.summarize(results, "update")
    assert cli.exit_code_for("update", summary) == cli.EXIT_ERROR


def test_exit_code_list_reports_unreachable_device():
    summary = cli.summarize([_result(success=False)], "list")
    assert cli.exit_code_for("list", summary) == cli.EXIT_ERROR


def test_exit_code_list_ignores_comparison():
    summary = cli.summarize([_result(latest_version="Unknown")], "list")
    assert cli.exit_code_for("list", summary) == cli.EXIT_OK


def test_render_human_labels_each_class():
    results = [
        _result(ip="192.168.8.191", needs_update=True, dns_name="flur"),
        _result(ip="192.168.8.192", dns_name="kueche"),
        _result(ip="192.168.8.193", latest_version="Unknown", dns_name="bad"),
        _result(ip="192.168.8.194", success=False, dns_name="keller"),
    ]
    text = cli.render_human("check", results, cli.summarize(results, "check"))
    assert "192.168.8.191" in text
    assert "Update verfügbar" in text
    assert "aktuell" in text
    assert "Vergleich unbekannt" in text
    assert "nicht erreichbar" in text


def test_render_human_uses_update_labels():
    results = [
        _result(ip="1", needs_update=True, update_completed=True),
        _result(ip="2"),
        _result(ip="3", success=False, update_started=True),
    ]
    text = cli.render_human("update", results, cli.summarize(results, "update"))
    assert "aktualisiert" in text
    assert "übersprungen" in text
    assert "Update fehlgeschlagen" in text
    assert "Update verfügbar" not in text


def test_render_human_ends_with_the_tally():
    results = [_result(needs_update=True)]
    text = cli.render_human("check", results, cli.summarize(results, "check"))
    assert text.splitlines()[-1] == "0 aktuell, 1 Update verfügbar, 0 Vergleich unbekannt, 0 Fehler"


def test_render_json_is_parseable_and_complete():
    results = [_result(needs_update=True)]
    summary = cli.summarize(results, "check")
    payload = json.loads(
        cli.render_json("check", "devices.yaml", results, summary, cli.EXIT_OUTDATED)
    )
    assert payload["command"] == "check"
    assert payload["devices_file"] == "devices.yaml"
    assert payload["exit_code"] == cli.EXIT_OUTDATED
    assert payload["summary"] == summary
    assert payload["results"][0]["ip"] == "192.168.8.191"


def test_render_json_passes_core_fields_through_unchanged():
    results = [_result(message="anything the core said")]
    payload = json.loads(cli.render_json("check", "d.yaml", results, {}, cli.EXIT_OK))
    assert payload["results"][0]["message"] == "anything the core said"


def test_render_human_list_no_comparison_wording():
    """list performs no release lookup, so comparison labels must not appear."""
    results = [
        {
            "ip": "192.168.8.191",
            "dns_name": "flur",
            "success": True,
            "current_version": "15.0.1",
        }
    ]
    text = cli.render_human("list", results, cli.summarize(results, "list"))
    assert "Vergleich unbekannt" not in text
    assert "aktuell" not in text
    assert "15.0.1" in text
    assert "192.168.8.191" in text


def test_render_human_list_marks_unreachable():
    """list marks unreachable devices with nicht erreichbar."""
    results = [{"ip": "192.168.8.192", "success": False, "current_version": "14.0.0"}]
    text = cli.render_human("list", results, cli.summarize(results, "list"))
    assert "nicht erreichbar" in text


def test_cmd_list_reports_firmware_without_release_lookup(monkeypatch):
    calls = []

    def fake_firmware(device):
        calls.append(device["ip"])
        return {"version": "15.0.1", "core_version": "2.7.4.9"}

    def explode():  # must never be called
        raise AssertionError("list must not perform a release lookup")

    monkeypatch.setattr(cli.updater, "get_device_firmware_version", fake_firmware)
    monkeypatch.setattr(cli.updater, "fetch_latest_tasmota_release", explode)

    devices = [{"ip": "192.168.8.191", "dns_name": "flur"}, {"ip": "192.168.8.192"}]
    results = cli.cmd_list(devices)

    assert calls == ["192.168.8.191", "192.168.8.192"]
    assert results[0] == {
        "ip": "192.168.8.191",
        "dns_name": "flur",
        "success": True,
        "current_version": "15.0.1",
    }
    assert "latest_version" not in results[0]


def test_cmd_list_marks_unreachable_device(monkeypatch):
    monkeypatch.setattr(cli.updater, "get_device_firmware_version", lambda device: None)
    results = cli.cmd_list([{"ip": "192.168.8.193"}])
    assert results[0]["success"] is False
    assert results[0]["current_version"] == "Unknown"


def test_cmd_list_treats_a_versionless_answer_as_a_failure(monkeypatch):
    monkeypatch.setattr(
        cli.updater,
        "get_device_firmware_version",
        lambda device: {"core_version": "2.7.4.9"},  # no "version" key
    )
    results = cli.cmd_list([{"ip": "192.168.8.194"}])
    assert results[0]["success"] is False
    assert results[0]["current_version"] == "Unknown"


def test_cmd_check_delegates_to_the_batch_runner(monkeypatch):
    seen = {}

    def fake_create(devices, check_only, update_only_needed, global_timeout, **kwargs):
        seen.update(
            devices=list(devices),
            check_only=check_only,
            update_only_needed=update_only_needed,
            global_timeout=global_timeout,
            background=kwargs.get("background"),
        )
        return "job-1"

    monkeypatch.setattr(cli.jobs, "create_batch_job", fake_create)
    monkeypatch.setattr(
        cli.jobs,
        "get_job",
        lambda job_id: {"status": "completed", "results": [_result()], "error": None},
    )

    results = cli.cmd_check([{"ip": "192.168.8.191"}])

    assert seen["check_only"] is True
    assert seen["update_only_needed"] is False
    assert seen["global_timeout"] is None
    assert seen["background"] is False
    assert results == [_result()]


def test_run_batch_raises_when_the_runner_refuses(monkeypatch):
    monkeypatch.setattr(cli.jobs, "create_batch_job", lambda *a, **k: None)
    with pytest.raises(cli.CliError, match="batch job"):
        cli.run_batch([{"ip": "1"}], check_only=True, timeout=None)


def test_run_batch_raises_on_runner_error(monkeypatch):
    monkeypatch.setattr(cli.jobs, "create_batch_job", lambda *a, **k: "job-1")
    monkeypatch.setattr(
        cli.jobs,
        "get_job",
        lambda job_id: {"status": "error", "results": [], "error": "boom"},
    )
    with pytest.raises(cli.CliError, match="boom"):
        cli.run_batch([{"ip": "1"}], check_only=True, timeout=None)


def test_cmd_update_only_touches_outdated_devices(monkeypatch):
    passes = []

    def fake_run_batch(devices, *, check_only, timeout):
        passes.append({"ips": [d["ip"] for d in devices], "check_only": check_only})
        if check_only:
            return [
                _result(ip="1", needs_update=True),
                _result(ip="2"),
            ]
        return [_result(ip="1", needs_update=True, update_completed=True, success=True)]

    monkeypatch.setattr(cli, "run_batch", fake_run_batch)

    results = cli.cmd_update([{"ip": "1"}, {"ip": "2"}], force=False, timeout=None)

    assert passes[0] == {"ips": ["1", "2"], "check_only": True}
    assert passes[1] == {"ips": ["1"], "check_only": False}
    by_ip = {r["ip"]: r for r in results}
    assert by_ip["1"]["update_completed"] is True
    assert by_ip["2"].get("update_completed") is None
    assert len(results) == 2


def test_cmd_update_skips_the_second_pass_when_nothing_is_outdated(monkeypatch):
    passes = []

    def fake_run_batch(devices, *, check_only, timeout):
        passes.append(check_only)
        return [_result(ip="1")]

    monkeypatch.setattr(cli, "run_batch", fake_run_batch)
    results = cli.cmd_update([{"ip": "1"}], force=False, timeout=None)

    assert passes == [True]
    assert results == [_result(ip="1")]


def test_cmd_update_does_not_flash_on_unknown_comparison(monkeypatch):
    passes = []

    def fake_run_batch(devices, *, check_only, timeout):
        passes.append(check_only)
        return [_result(ip="1", latest_version="Unknown")]

    monkeypatch.setattr(cli, "run_batch", fake_run_batch)
    results = cli.cmd_update([{"ip": "1"}], force=False, timeout=None)

    assert passes == [True], "an unknown comparison must not trigger a flash"
    assert cli.classify(results[0]) == "comparison_unknown"


def test_cmd_update_force_updates_every_reachable_device(monkeypatch):
    passes = []

    def fake_run_batch(devices, *, check_only, timeout):
        passes.append({"ips": [d["ip"] for d in devices], "check_only": check_only})
        if check_only:
            return [_result(ip="1"), _result(ip="2", success=False)]
        return [_result(ip="1", update_completed=True)]

    monkeypatch.setattr(cli, "run_batch", fake_run_batch)
    cli.cmd_update([{"ip": "1"}, {"ip": "2"}], force=True, timeout=None)

    assert passes[1] == {"ips": ["1"], "check_only": False}, "unreachable devices stay out"


def test_cmd_update_passes_the_timeout_to_the_second_pass_only(monkeypatch):
    seen = []

    def fake_run_batch(devices, *, check_only, timeout):
        seen.append((check_only, timeout))
        return [_result(ip="1", needs_update=True)] if check_only else [_result(ip="1")]

    monkeypatch.setattr(cli, "run_batch", fake_run_batch)
    cli.cmd_update([{"ip": "1"}], force=False, timeout=300)

    assert seen == [(True, None), (False, 300)]


def test_cmd_update_raises_when_the_flash_pass_drops_a_selected_device(monkeypatch):
    def fake_run_batch(devices, *, check_only, timeout):
        if check_only:
            return [
                _result(ip="1", needs_update=True),
                _result(ip="2", needs_update=True),
            ]
        return [_result(ip="1", needs_update=True, update_completed=True, success=True)]

    monkeypatch.setattr(cli, "run_batch", fake_run_batch)

    with pytest.raises(cli.CliError) as excinfo:
        cli.cmd_update([{"ip": "1"}, {"ip": "2"}], force=False, timeout=None)

    message = str(excinfo.value)
    assert re.search(r"no result for: 2$", message)
    assert "1" not in message.split("no result for:")[1]


def test_cmd_update_raises_without_calling_the_runner_when_the_whole_subset_is_unmapped(
    monkeypatch,
):
    calls = []

    def fake_run_batch(devices, *, check_only, timeout):
        calls.append(check_only)
        return [_result(ip="1", needs_update=True)]

    monkeypatch.setattr(cli, "run_batch", fake_run_batch)

    # "9" is not a configured device, so the selected IP from pass one can
    # never be mapped back to a device to flash — the subset is empty.
    with pytest.raises(cli.CliError, match=r"no result for: 1$"):
        cli.cmd_update([{"ip": "9"}], force=False, timeout=None)

    assert calls == [True], "the flash pass must not run against an empty subset"


def test_cmd_update_force_does_not_flash_a_device_with_unknown_comparison(monkeypatch):
    passes = []

    def fake_run_batch(devices, *, check_only, timeout):
        passes.append({"ips": [d["ip"] for d in devices], "check_only": check_only})
        if check_only:
            return [_result(ip="1", latest_version="Unknown")]
        return [_result(ip="1", update_completed=True)]

    monkeypatch.setattr(cli, "run_batch", fake_run_batch)
    results = cli.cmd_update([{"ip": "1"}], force=True, timeout=None)

    assert len(passes) == 1, "a device with an unknown comparison must never be flashed"
    assert results == [_result(ip="1", latest_version="Unknown")]


def test_main_writes_only_json_to_stdout_at_debug_level(monkeypatch, capsys, tmp_path):
    devices_file = tmp_path / "devices.yaml"
    devices_file.write_text("devices:\n  - ip: 192.168.8.191\n", encoding="utf-8")
    monkeypatch.setattr(cli, "cmd_check", lambda devices: [_result()])

    code = cli.main(["check", "-f", str(devices_file), "--json", "--log-level", "DEBUG"])

    captured = capsys.readouterr()
    assert code == cli.EXIT_OK
    assert json.loads(captured.out)["command"] == "check"


def test_main_reports_missing_devices_file(monkeypatch, capsys, tmp_path):
    code = cli.main(["check", "-f", str(tmp_path / "nope.yaml")])
    captured = capsys.readouterr()
    assert code == cli.EXIT_ERROR
    assert captured.out == ""
    assert "nope.yaml" in captured.err


def test_main_reports_empty_device_list(monkeypatch, capsys, tmp_path):
    devices_file = tmp_path / "devices.yaml"
    devices_file.write_text("devices: []\n", encoding="utf-8")
    code = cli.main(["check", "-f", str(devices_file)])
    captured = capsys.readouterr()
    assert code == cli.EXIT_ERROR
    assert "No devices" in captured.err


def test_main_rejects_duplicate_ips_before_touching_any_device(monkeypatch, capsys, tmp_path):
    devices_file = tmp_path / "devices.yaml"
    devices_file.write_text(
        "devices:\n  - ip: 192.168.8.191\n  - ip: 192.168.8.191\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        cli, "cmd_update", lambda *a, **k: pytest.fail("must not be called")
    )

    code = cli.main(["update", "-f", str(devices_file)])
    captured = capsys.readouterr()

    assert code == cli.EXIT_ERROR
    assert captured.out == ""
    assert "192.168.8.191" in captured.err


def test_main_turns_cli_errors_into_exit_two(monkeypatch, capsys, tmp_path):
    devices_file = tmp_path / "devices.yaml"
    devices_file.write_text("devices:\n  - ip: 1\n", encoding="utf-8")

    def explode(devices):
        raise cli.CliError("runner said no")

    monkeypatch.setattr(cli, "cmd_check", explode)
    code = cli.main(["check", "-f", str(devices_file)])
    assert code == cli.EXIT_ERROR
    assert "runner said no" in capsys.readouterr().err


def test_main_handles_interrupt_and_warns_about_the_running_flash(monkeypatch, capsys, tmp_path):
    devices_file = tmp_path / "devices.yaml"
    devices_file.write_text("devices:\n  - ip: 1\n", encoding="utf-8")

    def interrupt(devices, *, force, timeout):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "cmd_update", interrupt)
    code = cli.main(["update", "-f", str(devices_file)])
    err = capsys.readouterr().err
    assert code == cli.EXIT_ERROR
    assert "weiter" in err  # the flash keeps running on the device
