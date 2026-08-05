"""Spec §8. run_command executes on the host and never raises."""

import subprocess

import pytest

from zeroos.catalog import shell as catalog_shell
from zeroos.platform import shell as platform_shell
from zeroos.policy import gate as gate_module


class FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def spawned(monkeypatch, tmp_path):
    """Capture the argv instead of running it. No test touches a real shell."""
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return FakeCompleted(returncode=0, stdout="hello\n", stderr="")

    monkeypatch.setattr(platform_shell.subprocess, "run", fake_run)
    return calls


def test_the_argv_is_list_form_through_sh_c(spawned):
    platform_shell.run("echo hello && ls")
    argv, kwargs = spawned[0]
    assert argv == ["flatpak-spawn", "--host", "/bin/sh", "-c", "echo hello && ls"]
    assert "shell" not in kwargs
    assert kwargs["timeout"] == platform_shell.TIMEOUT_SECONDS


def test_the_working_directory_is_home(spawned, tmp_path):
    platform_shell.run("pwd")
    _argv, kwargs = spawned[0]
    assert str(kwargs["cwd"]) == str(tmp_path)


def test_exit_code_stdout_and_stderr_are_all_present(monkeypatch, tmp_path):
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    monkeypatch.setattr(
        platform_shell.subprocess,
        "run",
        lambda argv, **kw: FakeCompleted(returncode=1, stdout="out here", stderr="err here"),
    )
    result = platform_shell.run("false")
    assert result.startswith("exit 1")
    assert "out here" in result
    assert "--- stderr ---" in result
    assert "err here" in result


def test_a_silent_success_still_reports_its_exit_code(monkeypatch, tmp_path):
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    monkeypatch.setattr(
        platform_shell.subprocess,
        "run",
        lambda argv, **kw: FakeCompleted(returncode=0, stdout="", stderr=""),
    )
    assert platform_shell.run("true").strip() == "exit 0"


def test_a_timeout_is_reported_rather_than_raised(monkeypatch, tmp_path):
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))

    def timing_out(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=300)

    monkeypatch.setattr(platform_shell.subprocess, "run", timing_out)
    result = platform_shell.run("sleep 400")
    assert "five minutes" in result
    assert "exit" not in result.split("\n")[0]


def test_a_missing_flatpak_spawn_is_reported_rather_than_raised(monkeypatch, tmp_path):
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))

    def missing(argv, **kwargs):
        raise FileNotFoundError("flatpak-spawn")

    monkeypatch.setattr(platform_shell.subprocess, "run", missing)
    assert isinstance(platform_shell.run("ls"), str)


def test_the_platform_layer_does_not_cap(monkeypatch, tmp_path):
    """The cap belongs to the catalog binding. platform/ must not import
    catalog/ -- that is the dependency direction test_memory.py defends."""
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    monkeypatch.setattr(
        platform_shell.subprocess,
        "run",
        lambda argv, **kw: FakeCompleted(returncode=0, stdout="x" * 200_000, stderr=""),
    )
    assert len(platform_shell.run("cat huge")) > 200_000


def test_the_tool_caps_its_result(monkeypatch, tmp_path):
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    monkeypatch.setattr(platform_shell, "run", lambda command: "x" * 200_000)
    gate = gate_module.Gate(lambda rows: [True] * len(rows))
    run_command = catalog_shell.bind(gate)[0]
    gate.prepare([("run_command", {"command": "cat huge"})])
    result = run_command.call({"command": "cat huge"})
    assert len(result) < 41_000
    assert "cut off" in result


def test_the_tool_refuses_when_the_gate_says_no(monkeypatch, tmp_path):
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    monkeypatch.setattr(platform_shell, "run", lambda command: "exit 0")
    gate = gate_module.Gate(lambda rows: [False] * len(rows))
    run_command = catalog_shell.bind(gate)[0]
    gate.prepare([("run_command", {"command": "ls"})])
    assert run_command.call({"command": "ls"}) == gate_module.DENIED_MESSAGE


def test_the_tool_runs_when_the_gate_allows(monkeypatch, tmp_path):
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    monkeypatch.setattr(platform_shell, "run", lambda command: f"exit 0\n\n{command}")
    gate = gate_module.Gate(lambda rows: [True] * len(rows))
    run_command = catalog_shell.bind(gate)[0]
    gate.prepare([("run_command", {"command": "ls"})])
    assert "ls" in run_command.call({"command": "ls"})


def test_the_tool_name_and_schema(monkeypatch, tmp_path):
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    gate = gate_module.Gate(lambda rows: [True] * len(rows))
    run_command = catalog_shell.bind(gate)[0]
    assert run_command.name == "run_command"
    assert run_command.input_schema["properties"] == {
        "command": {"type": "string", "description": "The command to run."}
    }
    assert len(run_command.description) > 40
