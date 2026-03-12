import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ralph_tool"))
import ralph_harness as ralph


@pytest.fixture()
def isolated_paths(tmp_path, monkeypatch):
    state_dir = tmp_path / ".codex"
    monkeypatch.setattr(ralph, "STATE_DIR", state_dir)
    monkeypatch.setattr(ralph, "STATE_FILE", state_dir / "ralph-loop.local.md")
    monkeypatch.setattr(ralph, "LAST_MESSAGE_FILE", state_dir / "ralph-last-message.txt")
    monkeypatch.setattr(ralph, "USAGE_FILE", state_dir / "ralph-usage.local.json")
    monkeypatch.setattr(ralph, "ERR_FILE", state_dir / "ralph-last-error.log")
    monkeypatch.setattr(ralph, "RUNS_DIR", state_dir / "runs")
    monkeypatch.setattr(ralph, "CODEX_SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(ralph, "PROJECT_ROOT", tmp_path)

    implementer = tmp_path / "SPEC_FILES/smart_agents/2_SPEC_IMPLEMENTER.md"
    reviewer = tmp_path / "SPEC_FILES/smart_agents/3_SPEC_REVIEWER.md"
    implementer.parent.mkdir(parents=True, exist_ok=True)
    implementer.write_text("implementer", encoding="utf-8")
    reviewer.write_text("reviewer", encoding="utf-8")
    monkeypatch.setattr(ralph, "DEFAULT_IMPLEMENTER_PROMPT_FILE", implementer)
    monkeypatch.setattr(ralph, "DEFAULT_REVIEWER_PROMPT_FILE", reviewer)
    return tmp_path


def test_usage_text_and_loop_help_contains_new_options():
    assert "--max-review-cycles" in ralph.usage_text()
    assert "--max-review-cycles" in ralph.loop_help_text()
    assert "--prompt PATH" in ralph.usage_text()
    assert "--reviewer-prompt PATH" in ralph.loop_help_text()
    assert "--prompt file contents are used as PROMPT text" in ralph.usage_text()


def test_require_cmd_and_shutil_which_paths(monkeypatch):
    real_which = ralph.shutil_which
    monkeypatch.setattr(ralph, "shutil_which", lambda _c: "/usr/bin/codex")
    ralph.require_cmd("codex")
    monkeypatch.setattr(ralph, "shutil_which", lambda _c: None)
    with pytest.raises(ralph.RalphError, match="Required command not found"):
        ralph.require_cmd("codex")
    assert isinstance(real_which("python3"), str | type(None))


def test_frontmatter_parse_decode_and_update(isolated_paths):
    ralph.write_state_file(
        prompt="hello",
        max_iterations=2,
        max_review_cycles=3,
        completion_promise="DONE",
        codex_args_serialized="--model o3",
        run_id="run-1",
        artifact_dir="/tmp/run-1",
    )
    assert ralph.read_frontmatter_value(ralph.STATE_FILE, "iteration") == "1"
    assert ralph.read_frontmatter_value(ralph.STATE_FILE, "completion_promise") == "DONE"
    assert ralph.read_frontmatter_value(ralph.STATE_FILE, "missing") == ""

    ralph.update_state_value("iteration", 7)
    assert ralph.read_frontmatter_value(ralph.STATE_FILE, "iteration") == "7"

    raw, body = ralph.parse_frontmatter(ralph.STATE_FILE.read_text(encoding="utf-8"))
    assert raw["active"] == "true"
    assert body.strip() == "hello"
    assert ralph.parse_frontmatter("not frontmatter")[0] == {}
    assert ralph.parse_frontmatter("---\na: 1\nb: 2")[0] == {}
    assert ralph.parse_frontmatter("---\nno_colon\n---\n")[0] == {}
    assert ralph.decode_frontmatter_value('"abc"') == "abc"
    assert ralph.decode_frontmatter_value('"\\x"') == "\\x"
    assert ralph.decode_frontmatter_value("null") == ""


def test_read_frontmatter_and_update_missing_file(isolated_paths):
    missing = isolated_paths / "missing.md"
    assert ralph.read_frontmatter_value(missing, "x") == ""
    ralph.update_state_value("iteration", 2)


def test_extract_promise_helpers_and_review_status():
    text = "x <promise>A B</promise> y <promise>DONE</promise>"
    assert ralph.extract_promise_text(text) == "DONE"
    assert ralph.extract_promise_text("nope") is None
    assert ralph.parse_review_status("- Overall status: pass with nits") == "PASS WITH NITS"
    assert ralph.parse_review_status("Overall status: FAIL") == "FAIL"
    assert ralph.parse_review_status("unknown") is None


def test_extract_promise_text_from_file(isolated_paths):
    assert ralph.extract_promise_text_from_file(ralph.LAST_MESSAGE_FILE) is None
    ralph.LAST_MESSAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ralph.LAST_MESSAGE_FILE.write_text("x <promise>DONE</promise>", encoding="utf-8")
    assert ralph.extract_promise_text_from_file(ralph.LAST_MESSAGE_FILE) == "DONE"


def test_quote_frontmatter_and_now_iso():
    assert ralph.quote_frontmatter(None) == "null"
    assert ralph.quote_frontmatter(True) == "true"
    assert ralph.quote_frontmatter(5) == "5"
    assert ralph.quote_frontmatter("x") == '"x"'
    assert ralph.now_iso_utc().endswith("Z")
    assert ralph.format_duration_hms(3661) == "1h 1m 1s"
    resume_text = ralph.format_resume_time(0, 0)
    assert ":" in resume_text
    assert resume_text.endswith(("UTC", "EST", "EDT"))


def test_parse_loop_args_happy_and_stdin(monkeypatch):
    opts = ralph.parse_loop_args(
        [
            "hello",
            "world",
            "--max-iterations",
            "2",
            "--completion-promise",
            "X",
            "--prompt",
            "impl.md",
            "--reviewer-prompt",
            "review.md",
            "--weekly-limit-hours",
            "3",
            "--max-review-cycles",
            "4",
            "--max-transient-retries",
            "6",
            "--initial-backoff-seconds",
            "7",
            "--max-backoff-seconds",
            "8",
            "--",
            "--model",
            "o3",
        ],
        None,
    )
    assert opts.prompt == "hello world"
    assert opts.max_iterations == 2
    assert opts.completion_promise == "X"
    assert opts.implementer_prompt_path == "impl.md"
    assert opts.reviewer_prompt_path == "review.md"
    assert opts.weekly_limit_hours == "3"
    assert opts.max_review_cycles == 4
    assert opts.max_transient_retries == 6
    assert opts.initial_backoff_seconds == 7
    assert opts.max_backoff_seconds == 8
    assert opts.codex_args == ["--model", "o3"]

    opts2 = ralph.parse_loop_args([], "from stdin")
    assert opts2.prompt == "from stdin"
    monkeypatch.setenv("RALPH_WEEKLY_LIMIT_HOURS", "8")
    opts3 = ralph.parse_loop_args(["p"], None)
    assert opts3.weekly_limit_hours == "8"
    assert opts3.implementer_prompt_path == str(ralph.DEFAULT_IMPLEMENTER_PROMPT_FILE)
    assert opts3.reviewer_prompt_path == str(ralph.DEFAULT_REVIEWER_PROMPT_FILE)
    assert opts3.max_transient_retries == ralph.DEFAULT_MAX_TRANSIENT_RETRIES
    assert opts3.initial_backoff_seconds == ralph.DEFAULT_INITIAL_BACKOFF_SECONDS
    assert opts3.max_backoff_seconds == ralph.DEFAULT_MAX_BACKOFF_SECONDS
    monkeypatch.setenv("RALPH_WEEKLY_LIMIT_HOURS", "bad")
    with pytest.raises(ralph.RalphError, match="RALPH_WEEKLY_LIMIT_HOURS"):
        ralph.parse_loop_args(["p"], None)


def test_parse_loop_args_uses_prompt_file_when_prompt_omitted(tmp_path):
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("prompt from file", encoding="utf-8")
    opts = ralph.parse_loop_args(["--prompt", str(prompt_file)], None)
    assert opts.prompt == "prompt from file"
    assert opts.implementer_prompt_path == str(ralph.DEFAULT_IMPLEMENTER_PROMPT_FILE)
    assert opts.reviewer_prompt_path == str(ralph.DEFAULT_REVIEWER_PROMPT_FILE)


@pytest.mark.parametrize(
    "args,stdin_text,error",
    [
        (["--max-iterations"], None, "requires a number"),
        (["--max-iterations", "x"], None, "non-negative integer"),
        (["--completion-promise"], None, "requires a value"),
        (["--prompt"], None, "requires a file path"),
        (["--prompt", "does-not-exist.md"], None, "Prompt file not found"),
        (["--reviewer-prompt"], None, "requires a file path"),
        (["--weekly-limit-hours"], None, "requires a number"),
        (["--weekly-limit-hours", "x"], None, "must be 'auto'"),
        (["--max-review-cycles"], None, "requires a number"),
        (["--max-review-cycles", "x"], None, "non-negative integer"),
        (["--max-transient-retries"], None, "requires a number"),
        (["--max-transient-retries", "x"], None, "non-negative integer"),
        (["--initial-backoff-seconds"], None, "requires a number"),
        (["--initial-backoff-seconds", "x"], None, "non-negative integer"),
        (["--max-backoff-seconds"], None, "requires a number"),
        (["--max-backoff-seconds", "x"], None, "non-negative integer"),
        (["--", "--output-last-message"], "prompt", "Do not pass --output-last-message"),
        ([], None, "No prompt provided"),
    ],
)
def test_parse_loop_args_errors(args, stdin_text, error):
    with pytest.raises(ralph.RalphError, match=error):
        ralph.parse_loop_args(args, stdin_text)


def test_parse_loop_args_help_exits(capsys):
    with pytest.raises(SystemExit) as exc:
        ralph.parse_loop_args(["--help"], None)
    assert exc.value.code == 0
    assert "ralph loop" in capsys.readouterr().out


def test_ensure_usage_state_and_record_usage_segment(isolated_paths):
    ralph.USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ralph.USAGE_FILE.write_text(
        json.dumps(
            {
                "epoch": 1,
                "segments": [[1, 2], ["bad"], [5, 3]],
                "weekly_limit_seconds": 22,
            }
        ),
        encoding="utf-8",
    )
    ralph.ensure_usage_state(-1, now_epoch=100)
    state = json.loads(ralph.USAGE_FILE.read_text(encoding="utf-8"))
    assert state["weekly_limit_mode"] == "auto"
    assert state["weekly_limit_seconds"] == 22

    ralph.ensure_usage_state(1800, now_epoch=100)
    state = json.loads(ralph.USAGE_FILE.read_text(encoding="utf-8"))
    assert state["weekly_limit_mode"] == "manual"
    assert state["weekly_limit_seconds"] == 1800

    ralph.record_usage_segment(10, 20, now_epoch=50)
    state2 = json.loads(ralph.USAGE_FILE.read_text(encoding="utf-8"))
    assert [10, 20] in state2["segments"]
    ralph.record_usage_segment(4, 4, now_epoch=50)

    ralph.USAGE_FILE.write_text("{bad json", encoding="utf-8")
    ralph.ensure_usage_state(-1, now_epoch=100)
    assert json.loads(ralph.USAGE_FILE.read_text(encoding="utf-8"))["version"] == 1

    ralph.USAGE_FILE.write_text("{bad json", encoding="utf-8")
    ralph.record_usage_segment(2, 3, now_epoch=10)
    repaired = json.loads(ralph.USAGE_FILE.read_text(encoding="utf-8"))
    assert repaired["segments"] == [[2, 3]]

    ralph.USAGE_FILE.write_text(json.dumps({"segments": "bad"}), encoding="utf-8")
    ralph.record_usage_segment(4, 6, now_epoch=20)
    repaired2 = json.loads(ralph.USAGE_FILE.read_text(encoding="utf-8"))
    assert repaired2["segments"] == [[4, 6]]

    ralph.USAGE_FILE.write_text(json.dumps({"segments": [["a", "b"]]}), encoding="utf-8")
    ralph.ensure_usage_state(-1, now_epoch=100)
    cleaned = json.loads(ralph.USAGE_FILE.read_text(encoding="utf-8"))
    assert cleaned["segments"] == []

    ralph.USAGE_FILE.write_text(
        json.dumps({"segments": [[1], ["x", "y"], [3, 1]]}),
        encoding="utf-8",
    )
    ralph.record_usage_segment(6, 8, now_epoch=9)
    cleaned2 = json.loads(ralph.USAGE_FILE.read_text(encoding="utf-8"))
    assert cleaned2["segments"] == [[6, 8]]


def test_refresh_codex_rate_limits_no_session_and_with_session(isolated_paths):
    ralph.ensure_usage_state(-1, now_epoch=100)
    ralph.refresh_codex_rate_limits(now_epoch=200)
    state = json.loads(ralph.USAGE_FILE.read_text(encoding="utf-8"))
    assert "codex_primary_used_percent" not in state

    sessions = ralph.CODEX_SESSIONS_DIR / "x"
    sessions.mkdir(parents=True, exist_ok=True)
    rollout = sessions / "rollout-1.jsonl"
    token_payload = {
        "payload": {
            "type": "token_count",
            "rate_limits": {
                "primary": {"used_percent": 10.0, "window_minutes": 300, "resets_at": 1000},
                "secondary": {"used_percent": 2.0, "window_minutes": 10080, "resets_at": 2000},
            },
        }
    }
    rollout.write_text(json.dumps(token_payload) + "\n", encoding="utf-8")

    # Seed previous readings to hit median-estimation branch.
    current = json.loads(ralph.USAGE_FILE.read_text(encoding="utf-8"))
    current["last_primary_used_percent"] = 9.6
    current["last_secondary_used_percent"] = 1.95
    current["last_secondary_resets_at"] = 2000
    current["weekly_limit_mode"] = "auto"
    ralph.USAGE_FILE.write_text(json.dumps(current), encoding="utf-8")

    ralph.refresh_codex_rate_limits(now_epoch=300)
    updated = json.loads(ralph.USAGE_FILE.read_text(encoding="utf-8"))
    assert updated["codex_primary_used_percent"] == 10.0
    assert updated["codex_secondary_used_percent"] == 2.0
    assert updated["weekly_limit_seconds"] > 0

    noisy = sessions / "rollout-2.jsonl"
    noisy.write_text(
        "\n".join(
            [
                "{bad}",
                json.dumps({"payload": "bad"}),
                json.dumps({"payload": {"type": "not_token"}}),
                json.dumps(
                    {
                        "payload": {
                            "type": "token_count",
                            "rate_limits": {"primary": {}, "secondary": {}},
                        }
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    ralph.refresh_codex_rate_limits(now_epoch=301)


def test_refresh_codex_rate_limits_handles_missing_rate_and_open_error(isolated_paths, monkeypatch):
    ralph.USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ralph.USAGE_FILE.write_text("{oops", encoding="utf-8")
    ralph.refresh_codex_rate_limits(now_epoch=199)
    ralph.ensure_usage_state(-1, now_epoch=100)
    sessions = ralph.CODEX_SESSIONS_DIR
    sessions.mkdir(parents=True, exist_ok=True)
    bad = sessions / "rollout-bad.jsonl"
    bad.write_text(json.dumps({"payload": {"type": "token_count"}}), encoding="utf-8")
    ralph.refresh_codex_rate_limits(now_epoch=200)

    good = sessions / "rollout-good.jsonl"
    good.write_text("", encoding="utf-8")
    original_open = Path.open
    monkeypatch.setattr(
        Path,
        "open",
        lambda path_obj, *a, **k: (_ for _ in ()).throw(OSError("boom"))
        if str(path_obj).endswith("rollout-good.jsonl")
        else original_open(path_obj, *a, **k),
    )
    ralph.refresh_codex_rate_limits(now_epoch=201)

    weird = sessions / "x.jsonl"
    weird.write_text("{}", encoding="utf-8")
    stat_orig = Path.stat
    monkeypatch.setattr(
        Path,
        "stat",
        lambda path_obj, *a, **k: (_ for _ in ()).throw(OSError("stat"))
        if str(path_obj).endswith("x.jsonl")
        else stat_orig(path_obj, *a, **k),
    )
    ralph.refresh_codex_rate_limits(now_epoch=202)

    line = sessions / "rollout-values.jsonl"
    line.write_text(
        json.dumps(
            {
                "payload": {
                    "type": "token_count",
                    "rate_limits": {
                        "primary": {"used_percent": "bad", "window_minutes": "x", "resets_at": "x"},
                        "secondary": {"used_percent": "bad", "window_minutes": "x", "resets_at": "x"},
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    state = json.loads(ralph.USAGE_FILE.read_text(encoding="utf-8"))
    state["weekly_limit_estimates_seconds"] = "bad"
    state["last_primary_used_percent"] = 1.0
    state["last_secondary_used_percent"] = 1.0
    state["last_secondary_resets_at"] = 0
    ralph.USAGE_FILE.write_text(json.dumps(state), encoding="utf-8")
    ralph.refresh_codex_rate_limits(now_epoch=203)

    estimate = sessions / "rollout-estimate.jsonl"
    estimate.write_text(
        json.dumps(
            {
                "payload": {
                    "type": "token_count",
                    "rate_limits": {
                        "primary": {"used_percent": 10.0, "window_minutes": 300, "resets_at": 1000},
                        "secondary": {"used_percent": 2.0, "window_minutes": 10080, "resets_at": 0},
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    state2 = json.loads(ralph.USAGE_FILE.read_text(encoding="utf-8"))
    state2["weekly_limit_mode"] = "auto"
    state2["last_primary_used_percent"] = 9.6
    state2["last_secondary_used_percent"] = 1.95
    state2["last_secondary_resets_at"] = 0
    state2["weekly_limit_estimates_seconds"] = "bad"
    ralph.USAGE_FILE.write_text(json.dumps(state2), encoding="utf-8")
    ralph.refresh_codex_rate_limits(now_epoch=204)


def test_refresh_codex_rate_limits_stat_error_and_payload_filter(isolated_paths, monkeypatch):
    ralph.ensure_usage_state(-1, now_epoch=100)
    sessions = ralph.CODEX_SESSIONS_DIR
    sessions.mkdir(parents=True, exist_ok=True)

    staterr = sessions / "rollout-staterr.jsonl"
    staterr.write_text("{}", encoding="utf-8")
    stat_orig = Path.stat
    monkeypatch.setattr(
        Path,
        "stat",
        lambda path_obj, *a, **k: (_ for _ in ()).throw(OSError("stat"))
        if str(path_obj).endswith("rollout-staterr.jsonl")
        else stat_orig(path_obj, *a, **k),
    )
    ralph.refresh_codex_rate_limits(now_epoch=201)

    monkeypatch.setattr(Path, "stat", stat_orig)
    payload_bad = sessions / "rollout-payloadbad.jsonl"
    payload_bad.write_text(json.dumps({"payload": "oops"}), encoding="utf-8")
    ralph.refresh_codex_rate_limits(now_epoch=202)

    blank = sessions / "rollout-blank.jsonl"
    blank.write_text("\n", encoding="utf-8")
    ralph.refresh_codex_rate_limits(now_epoch=203)


def test_compute_usage_wait_seconds_paths():
    state = {
        "epoch": 0,
        "five_hour_window_seconds": 100,
        "five_hour_limit_seconds": 50,
        "weekly_window_seconds": 1000,
        "weekly_limit_seconds": 100,
        "codex_primary_used_percent": 100.0,
        "codex_secondary_used_percent": 100.0,
        "codex_primary_resets_at": 200,
        "codex_secondary_resets_at": 300,
        "segments": [[100, 180], [0, 20]],
    }
    wait, reason = ralph.compute_usage_wait_seconds(state, now=150)
    assert wait > 0
    assert "exhausted" in reason

    state2 = {
        "epoch": 0,
        "five_hour_window_seconds": 100,
        "five_hour_limit_seconds": 500,
        "weekly_window_seconds": 100,
        "weekly_limit_seconds": 10,
        "segments": [[0, 50]],
    }
    wait2, reason2 = ralph.compute_usage_wait_seconds(state2, now=60)
    assert wait2 >= 0
    assert isinstance(reason2, str)

    state3 = {
        "epoch": 0,
        "five_hour_window_seconds": 100,
        "five_hour_limit_seconds": 999,
        "weekly_window_seconds": 100,
        "weekly_limit_seconds": 10,
        "segments": [[0, 6], [1], ["x", 2]],
    }
    wait3, reason3 = ralph.compute_usage_wait_seconds(state3, now=50)
    assert wait3 > 0
    assert reason3 == "weekly pacing"

    state4 = {
        "epoch": 0,
        "five_hour_window_seconds": 100,
        "five_hour_limit_seconds": 0,
        "weekly_window_seconds": 100,
        "weekly_limit_seconds": 0,
        "segments": [],
    }
    wait4, reason4 = ralph.compute_usage_wait_seconds(state4, now=50)
    assert wait4 == 0
    assert isinstance(reason4, str)


def test_enforce_usage_limits_sleeps_once(isolated_paths, capsys):
    state = {
        "epoch": 0,
        "five_hour_window_seconds": 100,
        "five_hour_limit_seconds": 50,
        "codex_primary_used_percent": 100.0,
        "codex_primary_resets_at": 20,
        "segments": [],
    }
    ralph.USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ralph.USAGE_FILE.write_text(json.dumps(state), encoding="utf-8")

    calls = []

    def fake_sleep(seconds):
        calls.append(seconds)
        new_state = json.loads(ralph.USAGE_FILE.read_text(encoding="utf-8"))
        new_state["codex_primary_used_percent"] = 0.0
        new_state["codex_primary_resets_at"] = 0
        ralph.USAGE_FILE.write_text(json.dumps(new_state), encoding="utf-8")

    now_values = iter([10, 10])

    def fake_time():
        return next(now_values)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(ralph.time, "time", fake_time)
    try:
        ralph.enforce_usage_limits(fake_sleep)
    finally:
        monkeypatch.undo()
    assert calls
    output = capsys.readouterr().out
    assert "Sleeping 0h 0m 10s" in output
    assert "Planned resume:" in output


def test_enforce_usage_limits_handles_invalid_file(isolated_paths):
    ralph.USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ralph.USAGE_FILE.write_text("{invalid", encoding="utf-8")
    ralph.enforce_usage_limits(lambda _s: (_ for _ in ()).throw(RuntimeError("should not sleep")))


def test_usage_limit_detection_and_wait_parse():
    assert ralph.is_usage_limit_error("Too many requests; rate limit reached")
    assert not ralph.is_usage_limit_error("plain failure")
    assert ralph.parse_limit_wait_seconds("retry in 1h 2m") == 3720
    assert ralph.parse_limit_wait_seconds("retry in 3m 5s") == 185
    assert ralph.parse_limit_wait_seconds("retry in 8s") == 8
    assert ralph.parse_limit_wait_seconds("no timing") == 300


def test_prompt_builders_and_markdown_table():
    i_prompt = ralph.build_implementer_prompt("imp", "user", "DONE")
    assert "<ralph_user_prompt>" in i_prompt
    assert "<promise>DONE</promise>" in i_prompt

    r_prompt = ralph.build_reviewer_prompt("rev", "user", "DONE", ["a.py"], "git ok")
    assert "Overall status" in r_prompt
    assert "<promise>DONE</promise>" in r_prompt
    assert "Changed files from latest implementer pass" in r_prompt
    assert "a.py" in r_prompt

    table = ralph.markdown_table(["a", "b"], ["1", "2"])
    assert "| a | b |" in table


def test_artifact_and_git_helpers(isolated_paths, monkeypatch):
    ralph.write_text_file(isolated_paths / "x" / "a.txt", "hello")
    assert (isolated_paths / "x" / "a.txt").read_text(encoding="utf-8") == "hello"

    ralph.write_json_file(isolated_paths / "x" / "b.json", {"b": 1})
    assert json.loads((isolated_paths / "x" / "b.json").read_text(encoding="utf-8"))["b"] == 1

    assert ralph.summarize_stderr("a" * 200).endswith("...")
    assert ralph.classify_transient_failure("rate limit", 1) == "usage_limit"
    assert ralph.classify_transient_failure("connection reset by peer", 1) == "network"
    assert ralph.classify_transient_failure("fatal", -9) == "subprocess_interrupted"
    assert ralph.classify_transient_failure("fatal", 1) is None
    assert ralph.compute_backoff_delay(1, 0, 3) == 1
    assert ralph.compute_backoff_delay(4, 2, 5) == 5

    class Completed:
        def __init__(self, returncode, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    calls = iter(
        [
            Completed(0, stdout="abc123\n"),
            Completed(0, stdout="a.py\nb.py\n"),
            Completed(1, stderr="bad repo"),
            Completed(1, stderr="bad diff"),
        ]
    )
    monkeypatch.setattr(ralph.subprocess, "run", lambda *args, **kwargs: next(calls))
    baseline, note = ralph.detect_git_baseline(isolated_paths)
    assert baseline == "abc123"
    assert note is None
    changed, changed_note = ralph.collect_changed_files(isolated_paths, baseline)
    assert changed == ["a.py", "b.py"]
    assert changed_note is None
    baseline2, note2 = ralph.detect_git_baseline(isolated_paths)
    assert baseline2 is None
    assert note2 == "bad repo"
    changed2, changed_note2 = ralph.collect_changed_files(isolated_paths, "abc123")
    assert changed2 == []
    assert changed_note2 == "bad diff"
    changed3, changed_note3 = ralph.collect_changed_files(isolated_paths, None)
    assert changed3 == []
    assert "no baseline" in changed_note3

    monkeypatch.setattr(
        ralph.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("missing git")),
    )
    assert "git unavailable" in ralph.detect_git_baseline(isolated_paths)[1]
    assert "git unavailable" in ralph.collect_changed_files(isolated_paths, "abc123")[1]

    options = ralph.LoopOptions(
        "prompt",
        "impl.md",
        "review.md",
        2,
        "DONE",
        "auto",
        5,
        3,
        2,
        30,
        ["--model", "o3"],
    )
    run_context = ralph.RunContext("run-1", ralph.RUNS_DIR / "run-1", "abc123", None)
    manifest = ralph.run_manifest_payload(
        options=options,
        run_context=run_context,
        current_review_cycle=2,
        final_outcome="running",
    )
    assert manifest["run_id"] == "run-1"
    assert manifest["codex_args"] == ["--model", "o3"]
    ralph.write_run_manifest(
        options=options,
        run_context=run_context,
        current_review_cycle=2,
        final_outcome="running",
    )
    assert (run_context.run_dir / "run_manifest.json").exists()
    ralph.write_exec_artifacts(
        cycle_dir=run_context.run_dir / "review_cycle_001",
        prefix="implementer",
        prompt_text="p",
        last_message_text="m",
        stderr_text="e",
        result_payload={"ok": True},
    )
    assert (run_context.run_dir / "review_cycle_001" / "implementer_result.json").exists()


def test_read_prompt_file_missing_raises(isolated_paths):
    with pytest.raises(ralph.RalphError):
        ralph.read_prompt_file(Path("does-not-exist.md"))


def test_run_with_retries_success_and_missing_message(isolated_paths, monkeypatch):
    def fake_refresh():
        return None

    def fake_enforce():
        return None

    def fake_run(prompt, codex_args):
        assert prompt == "prompt"
        assert codex_args == ["--model", "o3"]
        ralph.LAST_MESSAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        ralph.LAST_MESSAGE_FILE.write_text("ok <promise>DONE</promise>", encoding="utf-8")
        return ralph.CommandResult(returncode=0, stderr="")

    monkeypatch.setattr(ralph, "run_codex_exec", fake_run)
    monkeypatch.setattr(ralph.time, "time", lambda: 10)
    result = ralph.run_with_retries(
        prompt="prompt",
        codex_args=["--model", "o3"],
        refresh_fn=fake_refresh,
        enforce_fn=fake_enforce,
        sleep_fn=lambda _: None,
        max_transient_retries=3,
        initial_backoff_seconds=2,
        max_backoff_seconds=30,
    )
    assert "DONE" in result.message
    assert result.elapsed_seconds == 0

    ralph.LAST_MESSAGE_FILE.unlink()

    def fake_run_no_message(prompt, codex_args):
        return ralph.CommandResult(returncode=0, stderr="")

    monkeypatch.setattr(ralph, "run_codex_exec", fake_run_no_message)
    with pytest.raises(ralph.RalphExecError, match="did not write"):
        ralph.run_with_retries(
            prompt="prompt",
            codex_args=[],
            refresh_fn=fake_refresh,
            enforce_fn=fake_enforce,
            sleep_fn=lambda _: None,
            max_transient_retries=3,
            initial_backoff_seconds=2,
            max_backoff_seconds=30,
        )


def test_run_with_retries_usage_retry_and_failure(isolated_paths, monkeypatch):
    calls = {"count": 0}

    def fake_refresh():
        return None

    def fake_enforce():
        return None

    def fake_run(prompt, codex_args):
        calls["count"] += 1
        if calls["count"] == 1:
            return ralph.CommandResult(returncode=1, stderr="rate limit retry in 2s")
        ralph.LAST_MESSAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        ralph.LAST_MESSAGE_FILE.write_text("Overall status: FAIL", encoding="utf-8")
        return ralph.CommandResult(returncode=0, stderr="")

    slept = []
    monkeypatch.setattr(ralph, "run_codex_exec", fake_run)
    result = ralph.run_with_retries(
        prompt="prompt",
        codex_args=[],
        refresh_fn=fake_refresh,
        enforce_fn=fake_enforce,
        sleep_fn=lambda seconds: slept.append(seconds),
        max_transient_retries=3,
        initial_backoff_seconds=2,
        max_backoff_seconds=30,
    )
    assert "FAIL" in result.message
    assert slept == [2]
    assert result.retry_attempts[0].classification == "usage_limit"

    monkeypatch.setattr(ralph, "run_codex_exec", lambda _p, _a: ralph.CommandResult(returncode=2, stderr="fatal"))
    with pytest.raises(ralph.RalphExecError, match="codex exec failed"):
        ralph.run_with_retries(
            prompt="prompt",
            codex_args=[],
            refresh_fn=fake_refresh,
            enforce_fn=fake_enforce,
            sleep_fn=lambda _: None,
            max_transient_retries=3,
            initial_backoff_seconds=2,
            max_backoff_seconds=30,
        )


def test_run_with_retries_transient_backoff_exhaustion(isolated_paths, monkeypatch):
    def fake_refresh():
        return None

    def fake_enforce():
        return None

    monkeypatch.setattr(
        ralph,
        "run_codex_exec",
        lambda _p, _a: ralph.CommandResult(returncode=1, stderr="connection reset by peer"),
    )
    slept = []
    with pytest.raises(ralph.RalphExecError) as exc:
        ralph.run_with_retries(
            prompt="prompt",
            codex_args=[],
            refresh_fn=fake_refresh,
            enforce_fn=fake_enforce,
            sleep_fn=lambda seconds: slept.append(seconds),
            max_transient_retries=1,
            initial_backoff_seconds=2,
            max_backoff_seconds=30,
        )
    assert slept == [2]
    assert exc.value.failure_reason == "transient_retry_exhausted:network"


def test_run_inner_loop_paths(isolated_paths, monkeypatch):
    ralph.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ralph.STATE_FILE.write_text("---\niteration: 1\n---\n\nbody", encoding="utf-8")

    monkeypatch.setattr(
        ralph,
        "run_with_retries",
        lambda **_: ralph.ExecResult("...<promise>DONE</promise>", 3),
    )
    result = ralph.run_inner_loop(
        loop_prompt="x",
        codex_args=[],
        completion_promise="DONE",
        max_iterations=2,
        refresh_fn=lambda: None,
        enforce_fn=lambda: None,
        sleep_fn=lambda _: None,
        max_transient_retries=3,
        initial_backoff_seconds=2,
        max_backoff_seconds=30,
    )
    assert result.promise_matched
    assert result.iterations_run == 1

    ralph.STATE_FILE.write_text("---\niteration: 1\n---\n\nbody", encoding="utf-8")

    monkeypatch.setattr(ralph, "run_with_retries", lambda **_: ralph.ExecResult("no promise", 2))
    result2 = ralph.run_inner_loop(
        loop_prompt="x",
        codex_args=[],
        completion_promise="DONE",
        max_iterations=1,
        refresh_fn=lambda: None,
        enforce_fn=lambda: None,
        sleep_fn=lambda _: None,
        max_transient_retries=3,
        initial_backoff_seconds=2,
        max_backoff_seconds=30,
    )
    assert result2.termination_reason == "max_iterations"

    ralph.STATE_FILE.unlink()
    with pytest.raises(SystemExit):
        ralph.run_inner_loop(
            loop_prompt="x",
            codex_args=[],
            completion_promise="DONE",
            max_iterations=1,
            refresh_fn=lambda: None,
            enforce_fn=lambda: None,
            sleep_fn=lambda _: None,
            max_transient_retries=3,
            initial_backoff_seconds=2,
            max_backoff_seconds=30,
        )

    ralph.STATE_FILE.write_text("---\niteration: 1\n---\n\nbody", encoding="utf-8")
    responses = iter([ralph.ExecResult("no", 1), ralph.ExecResult("...<promise>DONE</promise>", 1)])
    monkeypatch.setattr(ralph, "run_with_retries", lambda **_: next(responses))
    result3 = ralph.run_inner_loop(
        loop_prompt="x",
        codex_args=[],
        completion_promise="DONE",
        max_iterations=5,
        refresh_fn=lambda: None,
        enforce_fn=lambda: None,
        sleep_fn=lambda _: None,
        max_transient_retries=3,
        initial_backoff_seconds=2,
        max_backoff_seconds=30,
    )
    assert result3.iterations_run == 2

    ralph.STATE_FILE.write_text("---\niteration: 1\n---\n\nbody", encoding="utf-8")

    def run_and_delete(**_kwargs):
        ralph.STATE_FILE.unlink(missing_ok=True)
        return ralph.ExecResult("no", 1)

    monkeypatch.setattr(ralph, "run_with_retries", run_and_delete)
    with pytest.raises(SystemExit):
        ralph.run_inner_loop(
            loop_prompt="x",
            codex_args=[],
            completion_promise="DONE",
            max_iterations=5,
            refresh_fn=lambda: None,
            enforce_fn=lambda: None,
            sleep_fn=lambda _: None,
            max_transient_retries=3,
            initial_backoff_seconds=2,
            max_backoff_seconds=30,
        )


def test_run_reviewer_once_paths(monkeypatch):
    monkeypatch.setattr(
        ralph,
        "run_with_retries",
        lambda **_: ralph.ExecResult("# Review Summary\n- Overall status: PASS\n<promise>DONE</promise>", 4),
    )
    result = ralph.run_reviewer_once(
        reviewer_prompt="x",
        codex_args=[],
        completion_promise="DONE",
        refresh_fn=lambda: None,
        enforce_fn=lambda: None,
        sleep_fn=lambda _: None,
        max_transient_retries=3,
        initial_backoff_seconds=2,
        max_backoff_seconds=30,
    )
    assert result.status == "PASS"
    assert result.promise_matched

    monkeypatch.setattr(ralph, "run_with_retries", lambda **_: ralph.ExecResult("missing", 1))
    with pytest.raises(ralph.RalphError, match="missing 'Overall status'"):
        ralph.run_reviewer_once(
            reviewer_prompt="x",
            codex_args=[],
            completion_promise="DONE",
            refresh_fn=lambda: None,
            enforce_fn=lambda: None,
            sleep_fn=lambda _: None,
            max_transient_retries=3,
            initial_backoff_seconds=2,
            max_backoff_seconds=30,
        )


def test_run_loop_success_and_retry_and_caps(isolated_paths, monkeypatch):
    monkeypatch.setattr(ralph, "require_cmd", lambda _cmd: None)
    monkeypatch.setattr(ralph, "ensure_usage_state", lambda *_: None)
    monkeypatch.setattr(ralph, "refresh_codex_rate_limits", lambda: None)

    printed = []

    class DummyConsole:
        def print(self, value):
            printed.append(str(value))

    monkeypatch.setattr(ralph, "print_inner_status_table", lambda *args, **kwargs: printed.append("inner"))
    monkeypatch.setattr(ralph, "print_outer_status_table", lambda *args, **kwargs: printed.append("outer"))

    monkeypatch.setattr(
        ralph,
        "run_inner_loop",
        lambda **_: ralph.InnerLoopResult("completion_promise", 1, True, 1),
    )
    monkeypatch.setattr(
        ralph,
        "run_reviewer_once",
        lambda **_: ralph.ReviewerResult("PASS WITH NITS", True, 1),
    )

    options = ralph.LoopOptions(
        prompt="do thing",
        implementer_prompt_path=str(ralph.DEFAULT_IMPLEMENTER_PROMPT_FILE),
        reviewer_prompt_path=str(ralph.DEFAULT_REVIEWER_PROMPT_FILE),
        max_iterations=2,
        completion_promise="DONE",
        weekly_limit_hours="auto",
        max_review_cycles=5,
        max_transient_retries=3,
        initial_backoff_seconds=2,
        max_backoff_seconds=30,
        codex_args=[],
    )
    assert ralph.run_loop(options, console=DummyConsole(), sleep_fn=lambda _: None) == 0
    assert "inner" in printed
    assert "outer" in printed
    assert not ralph.STATE_FILE.exists()

    monkeypatch.setattr(
        ralph,
        "run_reviewer_once",
        lambda **_: ralph.ReviewerResult("FAIL", False, 1),
    )
    with pytest.raises(ralph.RalphError, match="unsatisfied"):
        ralph.run_loop(
            dataclasses_replace(options, max_review_cycles=1),
            console=DummyConsole(),
            sleep_fn=lambda _: None,
        )

    sequence = iter([
        ralph.ReviewerResult("FAIL", False, 1),
        ralph.ReviewerResult("PASS", True, 1),
    ])
    monkeypatch.setattr(ralph, "run_reviewer_once", lambda **_: next(sequence))
    assert ralph.run_loop(
        dataclasses_replace(options, max_review_cycles=5),
        console=DummyConsole(),
        sleep_fn=lambda _: None,
    ) == 0

    monkeypatch.setattr(
        ralph,
        "run_reviewer_once",
        lambda **_: ralph.ReviewerResult("PASS", False, 1),
    )
    with pytest.raises(ralph.RalphError, match="missing required completion"):
        ralph.run_loop(options, console=DummyConsole(), sleep_fn=lambda _: None)

    monkeypatch.setattr(
        ralph,
        "run_reviewer_once",
        lambda **_: ralph.ReviewerResult("MAYBE", False, 1),
    )
    with pytest.raises(ralph.RalphError, match="unrecognized reviewer status"):
        ralph.run_loop(options, console=DummyConsole(), sleep_fn=lambda _: None)


def test_run_loop_cancel_paths(isolated_paths, monkeypatch):
    monkeypatch.setattr(ralph, "require_cmd", lambda _cmd: None)
    monkeypatch.setattr(ralph, "ensure_usage_state", lambda *_: None)
    monkeypatch.setattr(ralph, "refresh_codex_rate_limits", lambda: None)
    monkeypatch.setattr(ralph, "write_state_file", lambda **_: None)
    rc = ralph.run_loop(
        ralph.LoopOptions(
            "p",
            str(ralph.DEFAULT_IMPLEMENTER_PROMPT_FILE),
            str(ralph.DEFAULT_REVIEWER_PROMPT_FILE),
            1,
            "DONE",
            "auto",
            1,
            3,
            2,
            30,
            [],
        ),
        console=type("C", (), {"print": lambda self, obj: None})(),
        sleep_fn=lambda _: None,
    )
    assert rc == 0

    def inner_and_cancel(**_kwargs):
        ralph.STATE_FILE.unlink(missing_ok=True)
        return ralph.InnerLoopResult("max_iterations", 1, False, 1)

        monkeypatch.setattr(
            ralph,
            "write_state_file",
            lambda **_: (ralph.STATE_FILE.parent.mkdir(parents=True, exist_ok=True), ralph.STATE_FILE.write_text("---\niteration: 1\n---\n\nx", encoding="utf-8")),
        )
    monkeypatch.setattr(ralph, "run_inner_loop", inner_and_cancel)
    rc2 = ralph.run_loop(
        ralph.LoopOptions(
            "p",
            str(ralph.DEFAULT_IMPLEMENTER_PROMPT_FILE),
            str(ralph.DEFAULT_REVIEWER_PROMPT_FILE),
            1,
            "DONE",
            "auto",
            1,
            3,
            2,
            30,
            [],
        ),
        console=type("C", (), {"print": lambda self, obj: None})(),
        sleep_fn=lambda _: None,
    )
    assert rc2 == 0


def dataclasses_replace(options, **kwargs):
    data = {
        "prompt": options.prompt,
        "implementer_prompt_path": options.implementer_prompt_path,
        "reviewer_prompt_path": options.reviewer_prompt_path,
        "max_iterations": options.max_iterations,
        "completion_promise": options.completion_promise,
        "weekly_limit_hours": options.weekly_limit_hours,
        "max_review_cycles": options.max_review_cycles,
        "max_transient_retries": options.max_transient_retries,
        "initial_backoff_seconds": options.initial_backoff_seconds,
        "max_backoff_seconds": options.max_backoff_seconds,
        "codex_args": options.codex_args,
    }
    data.update(kwargs)
    return ralph.LoopOptions(**data)


def test_cancel_status_and_usage_summary(isolated_paths, monkeypatch, capsys):
    assert ralph.cmd_cancel() == 0
    assert "No active" in capsys.readouterr().out

    ralph.write_state_file(
        prompt="hello",
        max_iterations=2,
        max_review_cycles=3,
        completion_promise="DONE",
        codex_args_serialized="--model o3",
        run_id="run-1",
        artifact_dir="/tmp/run-1",
    )
    assert ralph.cmd_cancel() == 0
    assert "Cancelled Ralph loop" in capsys.readouterr().out

    assert ralph.cmd_status() == 0
    assert "No active" in capsys.readouterr().out

    ralph.write_state_file(
        prompt="hello",
        max_iterations=2,
        max_review_cycles=3,
        completion_promise="DONE",
        codex_args_serialized="--model o3",
        run_id="run-2",
        artifact_dir="/tmp/run-2",
    )
    ralph.USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ralph.USAGE_FILE.write_text(
        json.dumps(
            {
                "epoch": 0,
                "five_hour_window_seconds": 100,
                "five_hour_limit_seconds": 10,
                "weekly_window_seconds": 100,
                "weekly_limit_seconds": 0,
                "weekly_limit_mode": "manual",
                "segments": [[0, 5]],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(ralph, "refresh_codex_rate_limits", lambda: None)
    assert ralph.cmd_status() == 0
    status_out = capsys.readouterr().out
    assert "Ralph loop active" in status_out
    assert "weekly_usage: disabled" in status_out
    lines = ralph.usage_summary_lines()
    assert any("5h_usage" in line for line in lines)

    ralph.USAGE_FILE.write_text("{bad", encoding="utf-8")
    assert ralph.usage_summary_lines() == ["  usage_limits: unavailable"]

    ralph.USAGE_FILE.write_text(
        json.dumps(
            {
                "epoch": 0,
                "five_hour_window_seconds": 100,
                "five_hour_limit_seconds": 10,
                "weekly_window_seconds": 100,
                "weekly_limit_seconds": 10,
                "weekly_limit_mode": "manual",
                "codex_primary_resets_at": 9999999999,
                "codex_secondary_resets_at": 9999999999,
                "codex_primary_used_percent": 50.0,
                "codex_secondary_used_percent": 30.0,
                "segments": [[0, 5]],
            }
        ),
        encoding="utf-8",
    )
    lines2 = ralph.usage_summary_lines()
    assert any("weekly_usage" in line for line in lines2)
    assert any("5h_usage_percent" in line for line in lines2)
    assert any("weekly_usage_percent" in line for line in lines2)

    ralph.USAGE_FILE.write_text(
        json.dumps(
            {
                "epoch": 0,
                "five_hour_window_seconds": 100,
                "five_hour_limit_seconds": 10,
                "weekly_window_seconds": 100,
                "weekly_limit_seconds": 0,
                "weekly_limit_mode": "auto",
                "segments": [],
            }
        ),
        encoding="utf-8",
    )
    assert any("auto-detecting" in line for line in ralph.usage_summary_lines())

    ralph.USAGE_FILE.write_text(
        json.dumps(
            {
                "epoch": 0,
                "five_hour_window_seconds": 100,
                "five_hour_limit_seconds": 10,
                "weekly_window_seconds": 100,
                "weekly_limit_seconds": 5,
                "weekly_limit_mode": "manual",
                "codex_secondary_resets_at": 0,
                "segments": [[0, 1]],
            }
        ),
        encoding="utf-8",
    )
    assert any("weekly_mode" in line for line in ralph.usage_summary_lines())

    # Cancel branch without iteration metadata.
    ralph.STATE_FILE.write_text("---\nactive: true\n---\n\nhello", encoding="utf-8")
    ralph.cmd_cancel()
    assert "Cancelled Ralph loop." in capsys.readouterr().out


def test_parse_stdin_and_cmd_loop_and_main(isolated_paths, monkeypatch, capsys):
    original_cmd_status = ralph.cmd_status
    class DummyStdin:
        def __init__(self, is_tty, text):
            self._is_tty = is_tty
            self._text = text

        def isatty(self):
            return self._is_tty

        def read(self):
            return self._text

    monkeypatch.setattr(ralph.sys, "stdin", DummyStdin(True, ""))
    assert ralph.parse_stdin_if_needed([]) is None
    monkeypatch.setattr(ralph.sys, "stdin", DummyStdin(False, "abc"))
    assert ralph.parse_stdin_if_needed([]) == "abc"
    assert ralph.parse_stdin_if_needed(["x"]) is None

    monkeypatch.setattr(ralph, "run_loop", lambda _opts, console: 0)
    assert ralph.cmd_loop(["prompt"], console=object()) == 0

    assert ralph.main(["help"]) == 0
    assert "Ralph Wiggum" in capsys.readouterr().out

    monkeypatch.setattr(ralph, "cmd_cancel", lambda: 3)
    assert ralph.main(["cancel"]) == 3

    monkeypatch.setattr(ralph, "cmd_status", lambda: 4)
    assert ralph.main(["status"]) == 4

    monkeypatch.setattr(ralph, "cmd_loop", lambda _rest, console: 5)
    assert ralph.main(["loop", "x"]) == 5

    assert ralph.main(["unknown"]) == 1
    out = capsys.readouterr()
    assert "Unknown command" in out.err

    # status path with state file but no usage file, and no codex args line.
    monkeypatch.setattr(ralph, "cmd_status", original_cmd_status)
    ralph.write_state_file(
        prompt="hello",
        max_iterations=2,
        max_review_cycles=3,
        completion_promise="DONE",
        codex_args_serialized="",
        run_id="run-3",
        artifact_dir="/tmp/run-3",
    )
    ralph.USAGE_FILE.unlink(missing_ok=True)
    assert ralph.cmd_status() == 0


def test_run_loop_cancelled_after_inner(isolated_paths, monkeypatch):
    monkeypatch.setattr(ralph, "require_cmd", lambda _cmd: None)
    monkeypatch.setattr(ralph, "ensure_usage_state", lambda *_: None)
    monkeypatch.setattr(ralph, "refresh_codex_rate_limits", lambda: None)
    monkeypatch.setattr(
        ralph,
        "write_state_file",
        lambda **_: (
            ralph.STATE_FILE.parent.mkdir(parents=True, exist_ok=True),
            ralph.STATE_FILE.write_text("---\niteration: 1\n---\n\nx", encoding="utf-8"),
        ),
    )
    monkeypatch.setattr(
        ralph,
        "run_inner_loop",
        lambda **_: ralph.InnerLoopResult("max_iterations", 1, False, 1),
    )
    monkeypatch.setattr(ralph, "print_inner_status_table", lambda *args, **kwargs: ralph.STATE_FILE.unlink(missing_ok=True))
    rc = ralph.run_loop(
        ralph.LoopOptions(
            "p",
            str(ralph.DEFAULT_IMPLEMENTER_PROMPT_FILE),
            str(ralph.DEFAULT_REVIEWER_PROMPT_FILE),
            1,
            "DONE",
            "auto",
            2,
            3,
            2,
            30,
            [],
        ),
        console=type("C", (), {"print": lambda self, obj: None})(),
        sleep_fn=lambda _: None,
    )
    assert rc == 0


def test_run_loop_uses_overridden_prompt_paths(isolated_paths, monkeypatch):
    monkeypatch.setattr(ralph, "require_cmd", lambda _cmd: None)
    monkeypatch.setattr(ralph, "ensure_usage_state", lambda *_: None)
    monkeypatch.setattr(ralph, "refresh_codex_rate_limits", lambda: None)
    monkeypatch.setattr(
        ralph,
        "write_state_file",
        lambda **_: (
            ralph.STATE_FILE.parent.mkdir(parents=True, exist_ok=True),
            ralph.STATE_FILE.write_text("---\niteration: 1\n---\n\nx", encoding="utf-8"),
        ),
    )
    monkeypatch.setattr(
        ralph,
        "run_inner_loop",
        lambda **_: ralph.InnerLoopResult("completion_promise", 1, True, 1),
    )
    monkeypatch.setattr(
        ralph,
        "run_reviewer_once",
        lambda **_: ralph.ReviewerResult("PASS", True, 1),
    )
    monkeypatch.setattr(ralph, "print_inner_status_table", lambda *args, **kwargs: None)
    monkeypatch.setattr(ralph, "print_outer_status_table", lambda *args, **kwargs: None)

    seen_paths = []

    def fake_read_prompt(path):
        seen_paths.append(str(path))
        return "agent prompt"

    monkeypatch.setattr(ralph, "read_prompt_file", fake_read_prompt)
    rc = ralph.run_loop(
        ralph.LoopOptions(
            prompt="work",
            implementer_prompt_path="custom-impl.md",
            reviewer_prompt_path="custom-review.md",
            max_iterations=1,
            completion_promise="DONE",
            weekly_limit_hours="auto",
            max_review_cycles=1,
            max_transient_retries=3,
            initial_backoff_seconds=2,
            max_backoff_seconds=30,
            codex_args=[],
        ),
        console=type("C", (), {"print": lambda self, obj: None})(),
        sleep_fn=lambda _: None,
    )
    assert rc == 0
    assert seen_paths == ["custom-impl.md", "custom-review.md"]


def test_run_loop_writes_artifacts_and_handles_failure_paths(isolated_paths, monkeypatch):
    monkeypatch.setattr(ralph, "require_cmd", lambda _cmd: None)
    monkeypatch.setattr(ralph, "ensure_usage_state", lambda *_: None)
    monkeypatch.setattr(ralph, "refresh_codex_rate_limits", lambda: None)
    monkeypatch.setattr(ralph, "print_inner_status_table", lambda *args, **kwargs: None)
    monkeypatch.setattr(ralph, "print_outer_status_table", lambda *args, **kwargs: None)
    monkeypatch.setattr(ralph, "generate_run_id", lambda now=None: "run-fixed")
    monkeypatch.setattr(ralph, "detect_git_baseline", lambda _root: ("base123", None))
    monkeypatch.setattr(ralph, "collect_changed_files", lambda _root, _base: (["src/a.py"], None))

    options = ralph.LoopOptions(
        prompt="work",
        implementer_prompt_path=str(ralph.DEFAULT_IMPLEMENTER_PROMPT_FILE),
        reviewer_prompt_path=str(ralph.DEFAULT_REVIEWER_PROMPT_FILE),
        max_iterations=1,
        completion_promise="DONE",
        weekly_limit_hours="auto",
        max_review_cycles=1,
        max_transient_retries=3,
        initial_backoff_seconds=2,
        max_backoff_seconds=30,
        codex_args=[],
    )
    monkeypatch.setattr(
        ralph,
        "run_inner_loop",
        lambda **_: ralph.InnerLoopResult("completion_promise", 1, True, 1, "impl msg", (), ""),
    )
    monkeypatch.setattr(
        ralph,
        "run_reviewer_once",
        lambda **kwargs: ralph.ReviewerResult("PASS", True, 1, kwargs["reviewer_prompt"], (), ""),
    )
    rc = ralph.run_loop(
        options,
        console=type("C", (), {"print": lambda self, obj: None})(),
        sleep_fn=lambda _: None,
    )
    assert rc == 0
    run_dir = ralph.RUNS_DIR / "run-fixed"
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["final_outcome"] == "completed"
    assert json.loads((run_dir / "review_cycle_001" / "implementer_result.json").read_text(encoding="utf-8"))[
        "changed_files"
    ] == ["src/a.py"]
    reviewer_prompt = (run_dir / "review_cycle_001" / "reviewer_prompt.txt").read_text(encoding="utf-8")
    assert "src/a.py" in reviewer_prompt

    monkeypatch.setattr(
        ralph,
        "run_inner_loop",
        lambda **_: (_ for _ in ()).throw(
            ralph.RalphExecError(
                "boom",
                failure_reason="transient_retry_exhausted:network",
                stderr="connection reset",
            )
        ),
    )
    with pytest.raises(ralph.RalphExecError):
        ralph.run_loop(dataclasses_replace(options), console=type("C", (), {"print": lambda self, obj: None})(), sleep_fn=lambda _: None)
    fail_manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert fail_manifest["failure_reason"] == "transient_retry_exhausted:network"
    assert (run_dir / "review_cycle_001" / "implementer_result.json").exists()

    monkeypatch.setattr(
        ralph,
        "run_inner_loop",
        lambda **_: ralph.InnerLoopResult("completion_promise", 1, True, 1, "msg", (), ""),
    )
    monkeypatch.setattr(
        ralph,
        "run_reviewer_once",
        lambda **_: (_ for _ in ()).throw(
            ralph.RalphExecError("boom", failure_reason="codex_exec_failed", stderr="fatal")
        ),
    )
    with pytest.raises(ralph.RalphExecError):
        ralph.run_loop(dataclasses_replace(options), console=type("C", (), {"print": lambda self, obj: None})(), sleep_fn=lambda _: None)
    reviewer_fail = json.loads((run_dir / "review_cycle_001" / "reviewer_result.json").read_text(encoding="utf-8"))
    assert reviewer_fail["status"] == "ERROR"

    ralph.LAST_MESSAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ralph.LAST_MESSAGE_FILE.write_text("bad reviewer output", encoding="utf-8")
    ralph.ERR_FILE.write_text("stderr", encoding="utf-8")
    monkeypatch.setattr(
        ralph,
        "run_reviewer_once",
        lambda **_: (_ for _ in ()).throw(ralph.RalphError("reviewer output missing 'Overall status' line")),
    )
    with pytest.raises(ralph.RalphError):
        ralph.run_loop(dataclasses_replace(options), console=type("C", (), {"print": lambda self, obj: None})(), sleep_fn=lambda _: None)
    reviewer_contract = json.loads((run_dir / "review_cycle_001" / "reviewer_result.json").read_text(encoding="utf-8"))
    assert reviewer_contract["failure_reason"] == "reviewer_contract_error"


def test_run_codex_exec_writes_err_file(isolated_paths, monkeypatch, capsys):
    class FakeStream:
        def __init__(self, content):
            self.content = content
            self.index = 0

        def read(self, _size=1):
            if self.index >= len(self.content):
                return ""
            char = self.content[self.index]
            self.index += 1
            return char

    class FakeStdin:
        def __init__(self):
            self.text = ""
            self.closed = False

        def write(self, text):
            self.text += text

        def close(self):
            self.closed = True

    class FakeProcess:
        def __init__(self, stdout_content, stderr_content, returncode=0):
            self.stdin = FakeStdin()
            self.stdout = FakeStream(stdout_content)
            self.stderr = FakeStream(stderr_content)
            self._returncode = returncode
            self.terminated = False
            self.killed = False
            self.wait_calls = 0

        def wait(self, timeout=None):
            self.wait_calls += 1
            return self._returncode

        def poll(self):
            return self._returncode if self.terminated else None

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.killed = True
            self.terminated = True

    class FakeSelector:
        def __init__(self):
            self.map = {}

        def register(self, fileobj, _events, data):
            self.map[fileobj] = data

        def unregister(self, fileobj):
            self.map.pop(fileobj, None)

        def select(self, timeout=None):
            for fileobj, data in list(self.map.items()):
                return [(type("K", (), {"fileobj": fileobj, "data": data})(), None)]
            return []

        def get_map(self):
            return self.map

        def close(self):
            self.map.clear()

    fake = FakeProcess("ok\n", "warn\n", 0)
    monkeypatch.setattr(ralph.subprocess, "Popen", lambda *args, **kwargs: fake)
    monkeypatch.setattr(ralph.selectors, "DefaultSelector", lambda: FakeSelector())

    result = ralph.run_codex_exec("prompt", ["--model", "o3"])
    assert result.returncode == 0
    assert ralph.ERR_FILE.read_text(encoding="utf-8") == "warn\n"
    captured = capsys.readouterr()
    assert "Ralph: starting codex exec..." in captured.out
    assert "ok" in captured.out
    assert "warn" in captured.err

    # Cover blank-line stdout branch and trailing stderr buffer branch.
    fake_empty = FakeProcess("\nX", "tail", 0)
    monkeypatch.setattr(ralph.subprocess, "Popen", lambda *args, **kwargs: fake_empty)
    result2 = ralph.run_codex_exec("prompt", [])
    assert result2.stderr == "tail"


def test_run_codex_exec_keyboard_interrupt_terminates_process(isolated_paths, monkeypatch):
    class FakeStream:
        def read(self, _size=1):
            return ""

    class FakeStdin:
        def write(self, _text):
            return None

        def close(self):
            return None

    class FakeProcess:
        def __init__(self):
            self.stdin = FakeStdin()
            self.stdout = FakeStream()
            self.stderr = FakeStream()
            self.terminated = False
            self.killed = False
            self.wait_count = 0

        def wait(self, timeout=None):
            self.wait_count += 1
            if self.wait_count == 1:
                raise ralph.subprocess.TimeoutExpired("codex", timeout)
            return 130

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.killed = True

    class InterruptSelector:
        def __init__(self):
            self.map = {"x": "y"}

        def register(self, fileobj, _events, data):
            self.map[fileobj] = data

        def unregister(self, fileobj):
            self.map.pop(fileobj, None)

        def select(self, timeout=None):
            raise KeyboardInterrupt()

        def get_map(self):
            return self.map

        def close(self):
            self.map.clear()

    fake = FakeProcess()
    monkeypatch.setattr(ralph.subprocess, "Popen", lambda *args, **kwargs: fake)
    monkeypatch.setattr(ralph.selectors, "DefaultSelector", lambda: InterruptSelector())
    with pytest.raises(ralph.RalphError, match="interrupted by user"):
        ralph.run_codex_exec("prompt", [])
    assert fake.terminated
    assert fake.killed


def test_run_codex_exec_periodic_color_reset(isolated_paths, monkeypatch, capsys):
    class FakeStream:
        def __init__(self, content):
            self.content = content
            self.index = 0

        def read(self, _size=1):
            if self.index >= len(self.content):
                return ""
            char = self.content[self.index]
            self.index += 1
            return char

    class FakeStdin:
        def write(self, _text):
            return None

        def close(self):
            return None

    class FakeProcess:
        def __init__(self):
            self.stdin = FakeStdin()
            self.stdout = FakeStream("x")
            self.stderr = FakeStream("")
            self.returncode = 0

        def wait(self, timeout=None):
            return self.returncode

        def poll(self):
            return self.returncode

        def terminate(self):
            return None

        def kill(self):
            return None

    class StepSelector:
        def __init__(self):
            self.map = {}
            self.step = 0

        def register(self, fileobj, _events, data):
            self.map[fileobj] = data

        def unregister(self, fileobj):
            self.map.pop(fileobj, None)

        def select(self, timeout=None):
            self.step += 1
            if self.step <= 3:
                return []
            for fileobj, data in list(self.map.items()):
                return [(type("K", (), {"fileobj": fileobj, "data": data})(), None)]
            return []

        def get_map(self):
            return self.map

        def close(self):
            self.map.clear()

    monotonic_values = iter([0.0, 3.0, 3.1, 3.2, 3.3, 3.4, 3.5])
    monkeypatch.setattr(ralph.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(ralph.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(ralph.selectors, "DefaultSelector", lambda: StepSelector())

    result = ralph.run_codex_exec("prompt", [])
    assert result.returncode == 0
    captured = capsys.readouterr()
    assert ralph.ANSI_COLOR_RESET in captured.out or ralph.ANSI_COLOR_RESET in captured.err


def test_print_status_tables_render_markdown():
    rendered = []

    class Console:
        def print(self, obj):
            rendered.append(str(obj))

    ralph.print_inner_status_table(
        Console(),
        review_cycle=1,
        result=ralph.InnerLoopResult("completion_promise", 2, True, 7),
        next_action="run_reviewer",
    )
    ralph.print_outer_status_table(
        Console(),
        review_cycle=1,
        result=ralph.ReviewerResult("FAIL", False, 3),
        decision="retry_implementer",
    )

    assert len(rendered) == 2


def test_cli_entrypoint_keyboard_interrupt_handled(monkeypatch):
    import runpy
    import types
    from pathlib import Path

    entrypoint = Path(__file__).resolve().parents[1] / "ralph_tool" / "ralph.py"

    fake_harness = types.SimpleNamespace()
    fake_harness.RalphError = ralph.RalphError
    fake_harness.main = lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt())
    errors = []
    fake_harness.err = lambda msg: errors.append(msg)
    monkeypatch.setitem(sys.modules, "ralph_harness", fake_harness)

    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(entrypoint), run_name="__main__")
    assert exc.value.code == 130
    assert errors == ["Ralph cancelled by user"]
