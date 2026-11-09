"""Phase A fix 4, G1: the tick owns the `Running:` line (AS-1, AS-2). Fakes only."""

import json

import chief_tick as c
import pytest
import usage_guard as g

NOW = 1_800_000_000.0  # 16:00 SGT


def usage():
    return g.Usage(10, 10, NOW + 3600, NOW + 86400, NOW)


class FakeGh:
    def __call__(self, args):
        return "[]"


@pytest.fixture
def status_file(tmp_path):
    f = tmp_path / "STATUS.md"
    f.write_text("# STATUS\nUsage: x\nStopped: no\n## Where we are\n- Next: Phase 7\n## Log\n",
                 encoding="utf-8")
    return f


def start(status_file, agent="chief"):
    g.state_path().unlink(missing_ok=True)
    return c.start_background(agent, "p", "s", "", lambda: usage(), FakeGh(), status_file, NOW,
                              lambda: None, lambda a, p: 4242)


def write_running(**over):
    data = {"agent": "chief", "stage": "s", "phase": "", "prompt": "p", "pid": 4242,
            "started": NOW - 10, "five_hour_before": 10, "weekly_before": 11}
    c._write_note(c.running_path(), {**data, **over})


def running_lines(status_file):
    return [x for x in status_file.read_text(encoding="utf-8").splitlines() if "Running:" in x]


def tick(status_file, alive=lambda pid: True):
    return c.tick(lambda: usage(), FakeGh(), None, status_file, NOW, lambda: None, alive,
                  lambda pid: None)


def test_as1_launch_writes_the_line_from_the_real_start_time(status_file):
    assert start(status_file) == "started chief"
    assert running_lines(status_file) == ["Running: chief since 16:00 SGT"]


def test_as1_the_line_is_gone_when_the_tick_records_a_finished_worker(status_file):
    start(status_file)
    c._write_note(c.done_path(), {"agent": "chief", "exit_code": 0, "finished": NOW,
                                  "stdout": json.dumps({"result": "ok"})})
    tick(status_file)
    assert running_lines(status_file) == []


def test_the_line_is_gone_when_a_worker_vanished(status_file):
    start(status_file)
    tick(status_file, alive=lambda pid: False)
    assert running_lines(status_file) == []


def test_the_line_is_gone_when_a_worker_ran_over_time(status_file):
    start(status_file)
    c._write_note(c.running_path(), {**json.loads(c.running_path().read_text()),
                                     "started": NOW - 7 * 3600})
    tick(status_file)
    assert running_lines(status_file) == []


def test_the_line_is_gone_when_stopped_by_hand(status_file):
    start(status_file)
    c.stop_worker(lambda: usage(), status_file, NOW, alive=lambda pid: True, killer=lambda p: None)
    assert running_lines(status_file) == []


def test_the_line_stays_while_the_worker_runs(status_file):
    start(status_file)
    assert tick(status_file) == "busy"
    assert len(running_lines(status_file)) == 1


def test_as2_a_running_line_without_a_worker_is_deleted_with_one_log_line(status_file):
    c.status.set_running(status_file, "builder", "22:30 SGT")  # a hand-made, wrong line
    assert not c.running_path().exists() and len(running_lines(status_file)) == 1
    tick(status_file)
    assert running_lines(status_file) == []
    tick(status_file)  # nothing more to remove: no second Log line
    assert status_file.read_text(encoding="utf-8").count("Running line removed: no worker") == 1


def test_a_running_line_does_not_hide_the_next_line_from_has_work(status_file):
    c.status.set_running(status_file, "chief", "16:00 SGT")
    assert c.has_work(status_file.read_text(encoding="utf-8"))
