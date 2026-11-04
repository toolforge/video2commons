"""Tests for the cleanup that ends every task of the worker.

Whatever happens during a task (success, error, abort, or a failure of the
cleanup itself), the worker must remove the task's files, forget the user's
OAuth tokens and update the stats, without changing the outcome of the task.
"""

import collections
import os
from types import SimpleNamespace

import pytest
import pywikibot
from celery.exceptions import Ignore, Retry

from video2commons.backend import worker
from video2commons.exceptions import TaskAbort, TaskError

TASK_ID = "00000000-0000-4000-8000-000000000000"
FILENAME = "Example video"
FILE_URL = "https://commons.wikimedia.org/wiki/File:Example_video.webm"

# Description of each cleanup step in the log, and the key of its result in
# cleanup_state(). Publishing the status leaves no state to check.
CLEANUP_STEPS = {
    "status": "publish the cleanup status",
    "stopme": "stop Pywikibot",
    "authenticate": "forget the OAuth tokens",
    "usernames": "forget the username",
    "sites": "forget the cached sites",
    "output": "remove the output directory",
    "stats": "update the stats",
}
ALL_CLEANED_UP = {
    "stopme": True,
    "authenticate": True,
    "usernames": True,
    "sites": True,
    "output": True,
    "stats": True,
}


class FakeRedis:
    """The few Redis commands that the worker runs itself."""

    def __init__(self):
        self.locked = False

    def exists(self, key):
        return self.locked

    def setex(self, key, ttl, value):
        pass


class FailingDict(dict):
    """A dict that can be filled but not cleared."""

    def clear(self):
        raise RuntimeError("clear() failed")


class TaskRun:
    """What a task does, and what the worker did during it."""

    def __init__(self):
        self.redis = FakeRedis()
        self.aborted = False
        self.free_bytes = 100 << 30
        # Name of the stage during which the user aborts the task.
        self.abort_during = None
        # Abort the task right after the "Done!" status has been published.
        self.abort_after_done = False
        # Abort the task right before a stage fails.
        self.abort_on_failure = False
        # Exception raised by a stage, and value returned by a stage.
        self.failures = {}
        self.results = {}
        # Cleanup steps that fail.
        self.failing_steps = set()

        self.outputdir = None
        self.statuses = []
        self.stats = []
        self.stopped = 0

    def stage(self, name, statuscallback=None):
        """Run the checks that a real stage would run while working."""
        if self.abort_during == name:
            self.aborted = True
        if statuscallback:
            statuscallback(None, 50)
        if name in self.failures:
            if self.abort_on_failure:
                self.aborted = True
            raise self.failures[name]


@pytest.fixture
def run(monkeypatch, tmp_path):
    """Replace everything the worker talks to with fakes."""
    task_run = TaskRun()

    monkeypatch.setattr(worker, "redisconnection", task_run.redis)
    monkeypatch.setattr(worker, "OUTPUT_DIR", f"{tmp_path}/output/")
    monkeypatch.setattr(
        worker.os,
        "statvfs",
        lambda path: SimpleNamespace(f_frsize=1, f_bavail=task_run.free_bytes),
        raising=False,
    )

    def update_task_stats(conn, task_id, remove=False):
        assert task_id == TASK_ID
        if remove and "stats" in task_run.failing_steps:
            raise ConnectionError("Redis is unreachable")
        task_run.stats.append(remove)

    monkeypatch.setattr(worker, "update_task_stats", update_task_stats)

    # Task state and notifications, which go to Redis.
    def update_state(self, state=None, meta=None, **kwargs):
        text = meta["text"]
        if text == "Cleaning up..." and "status" in task_run.failing_steps:
            raise ConnectionError("Redis is unreachable")
        task_run.statuses.append(text)
        if text == "Done!" and task_run.abort_after_done:
            task_run.aborted = True

    monkeypatch.setattr(worker.EncodingTask, "update_state", update_state)
    monkeypatch.setattr(
        worker.EncodingTask, "is_aborted", lambda self, **kwargs: task_run.aborted
    )
    monkeypatch.setattr(worker, "publish_notification", lambda *args: None)
    monkeypatch.setattr(worker, "get_task_status", lambda *args: {})

    def retry(self, **kwargs):
        raise Retry()

    monkeypatch.setattr(worker.EncodingTask, "retry", retry)

    # The stages of a task.
    def download(conn, url, ie_key, key, subtitles, outputdir, status, error):
        task_run.outputdir = outputdir
        target = os.path.join(outputdir, "source.mkv")
        open(target, "wb").close()
        task_run.stage("download", status)
        return task_run.results.get("download", {"target": target, "subtitles": {}})

    def encode(source, key, status, error, concurrency):
        target = source + ".av1.webm"
        open(target, "wb").close()
        task_run.stage("encode", status)
        return task_run.results.get("encode", target)

    def upload(file, filename, url, filedesc, username, status, error):
        task_run.stage("upload", status)
        return task_run.results.get("upload", (filename, FILE_URL))

    monkeypatch.setattr(worker.download, "download", download)
    monkeypatch.setattr(worker.encode, "encode", encode)
    monkeypatch.setattr(worker.upload, "upload", upload)
    monkeypatch.setattr(worker.categories, "get_inferable_categories", lambda f: [])
    monkeypatch.setattr(
        worker.categories, "get_subtitle_categories", lambda f, langs: []
    )
    monkeypatch.setattr(
        worker.categories, "append_categories", lambda desc, categories: desc
    )

    # Pywikibot, with the global state that the cleanup must reset.
    class Site:
        def __init__(self, code, fam, user):
            pywikibot._sites[(code, fam, user)] = self

        def login(self):
            task_run.stage("login")

    def stopme():
        if "stopme" in task_run.failing_steps:
            raise RuntimeError("stopme() failed")
        task_run.stopped += 1

    monkeypatch.setattr(pywikibot, "Site", Site)
    monkeypatch.setattr(pywikibot, "stopme", stopme)
    monkeypatch.setattr(pywikibot, "_sites", {})
    monkeypatch.setattr(pywikibot.config, "authenticate", {})
    monkeypatch.setattr(pywikibot.config, "usernames", collections.defaultdict(dict))

    def fail_steps(*steps):
        """Make some cleanup steps fail."""
        task_run.failing_steps.update(steps)
        if "authenticate" in steps:
            monkeypatch.setattr(pywikibot.config, "authenticate", FailingDict())
        if "usernames" in steps:
            monkeypatch.setattr(
                pywikibot.config, "usernames", collections.defaultdict(FailingDict)
            )
        if "sites" in steps:
            monkeypatch.setattr(pywikibot, "_sites", FailingDict())
        if "output" in steps:

            def rmtree(path):
                raise PermissionError(f"Cannot remove {path}")

            monkeypatch.setattr(worker, "shutil", SimpleNamespace(rmtree=rmtree))

    task_run.fail_steps = fail_steps

    worker.main.push_request(id=TASK_ID, hostname="celery@encoding01")
    yield task_run
    worker.main.pop_request()


def start_task():
    """Run the task in the current process, as a worker does."""
    return worker.main.run(
        "https://example.org/video",
        "Generic",
        False,
        FILENAME,
        "== Summary ==",
        "bestvideo+bestaudio/best",
        "av1.webm",
        "Example",
        ("access-token", "access-secret"),
    )


def cleanup_state(run):
    """Which cleanup steps have done their job."""
    return {
        "stopme": run.stopped == 1,
        "authenticate": not pywikibot.config.authenticate,
        "usernames": not pywikibot.config.usernames["commons"],
        "sites": not pywikibot._sites,
        "output": run.outputdir is not None and not os.path.exists(run.outputdir),
        "stats": run.stats == [False, True],
    }


def cleanup_errors(caplog):
    """The cleanup steps that failed, according to the log."""
    return {
        step
        for step, description in CLEANUP_STEPS.items()
        for record in caplog.records
        if record.getMessage() == f"Could not {description} of task {TASK_ID}"
    }


# Outcomes of a task: how to get them, and the exception that ends the task.
# They happen during the upload, so that every cleanup step has work to do.
OUTCOMES = {
    "success": (lambda run: None, None, None),
    "error": (
        lambda run: run.results.update(upload=(FILENAME, None)),
        TaskError,
        "^Upload failed!$",
    ),
    "abort": (lambda run: setattr(run, "abort_during", "upload"), TaskAbort, None),
}


def check_outcome(outcome):
    """Run the task and check that it ends as expected for this outcome."""
    _, expected, message = OUTCOMES[outcome]
    if expected is None:
        assert start_task() == {
            "type": "done",
            "filename": f"{FILENAME}.webm",
            "url": FILE_URL,
        }
        return

    with pytest.raises(expected, match=message) as excinfo:
        start_task()
    # TaskAbort is a TaskError: check that an error isn't replaced with the
    # TaskAbort of the cleanup.
    assert type(excinfo.value) is expected


def test_success(run, caplog):
    check_outcome("success")

    assert run.statuses[-2:] == ["Done!", "Cleaning up..."]
    assert cleanup_state(run) == ALL_CLEANED_UP
    assert cleanup_errors(caplog) == set()


@pytest.mark.parametrize("stage", ["download", "encode", "upload"])
def test_abort(run, caplog, stage):
    run.abort_during = stage

    with pytest.raises(TaskAbort):
        start_task()

    # The status of an aborted task can't be updated anymore, which isn't a
    # cleanup failure.
    assert "Cleaning up..." not in run.statuses
    assert cleanup_state(run) == ALL_CLEANED_UP
    assert cleanup_errors(caplog) == set()


def test_abort_after_upload_keeps_success(run, caplog):
    # The file is on Commons: an abort that comes too late must not turn the
    # task into a failure.
    run.abort_after_done = True

    check_outcome("success")

    assert cleanup_state(run) == ALL_CLEANED_UP
    assert cleanup_errors(caplog) == set()


@pytest.mark.parametrize(
    ("stage", "failure", "result", "expected", "message"),
    [
        ("download", None, None, TaskError, "^Download failed!$"),
        ("download", TaskError("No video found"), None, TaskError, "^No video found$"),
        ("encode", None, None, TaskError, "^Convert failed!$"),
        ("encode", RuntimeError("ffmpeg crashed"), None, RuntimeError, "ffmpeg"),
        (
            "login",
            pywikibot.exceptions.NoUsernameError("No username"),
            None,
            TaskError,
            "^pywikibot.Error: NoUsernameError: No username$",
        ),
        (
            "upload",
            pywikibot.exceptions.Error("Upload warning"),
            None,
            TaskError,
            "^pywikibot.Error: Error: Upload warning$",
        ),
        ("upload", None, (FILENAME, None), TaskError, "^Upload failed!$"),
        # Not errors, but they must not skip the cleanup either.
        ("encode", SystemExit(1), None, SystemExit, None),
        ("encode", KeyboardInterrupt(), None, KeyboardInterrupt, None),
    ],
)
def test_error(run, caplog, stage, failure, result, expected, message):
    if failure is not None:
        run.failures[stage] = failure
    else:
        run.results[stage] = result

    with pytest.raises(expected, match=message) as excinfo:
        start_task()

    assert type(excinfo.value) is expected
    assert run.statuses[-1] == "Cleaning up..."
    assert cleanup_state(run) == ALL_CLEANED_UP
    assert cleanup_errors(caplog) == set()


def test_abort_during_error_keeps_error(run, caplog):
    # The cleanup must not replace the error with the TaskAbort raised by its
    # status update.
    run.failures["encode"] = RuntimeError("ffmpeg crashed")
    run.abort_on_failure = True

    with pytest.raises(RuntimeError, match="ffmpeg crashed"):
        start_task()

    assert cleanup_state(run) == ALL_CLEANED_UP
    assert cleanup_errors(caplog) == set()


@pytest.mark.parametrize("outcome", OUTCOMES)
@pytest.mark.parametrize("step", CLEANUP_STEPS)
def test_failing_cleanup_step(run, caplog, outcome, step):
    OUTCOMES[outcome][0](run)
    run.fail_steps(step)

    check_outcome(outcome)

    # The status of an aborted task is never published, so it can't fail.
    expected_errors = set() if (step, outcome) == ("status", "abort") else {step}
    assert cleanup_errors(caplog) == expected_errors
    # Every other step has still done its job.
    expected_state = dict(ALL_CLEANED_UP)
    if step in expected_state:
        expected_state[step] = False
    assert cleanup_state(run) == expected_state


@pytest.mark.parametrize("outcome", OUTCOMES)
def test_every_cleanup_step_failing(run, caplog, outcome):
    OUTCOMES[outcome][0](run)
    run.fail_steps(*CLEANUP_STEPS)

    check_outcome(outcome)

    expected_errors = set(CLEANUP_STEPS)
    if outcome == "abort":
        expected_errors.remove("status")
    assert cleanup_errors(caplog) == expected_errors
    assert cleanup_state(run) == dict.fromkeys(ALL_CLEANED_UP, False)


def test_locked_task_is_ignored(run):
    # Another worker already runs this task: nothing to clean up.
    run.redis.locked = True

    with pytest.raises(Ignore):
        start_task()

    assert run.outputdir is None
    assert not os.path.exists(worker.OUTPUT_DIR)
    assert run.stats == []
    assert run.stopped == 0


def test_retry_when_disk_is_full(run):
    run.free_bytes = 1 << 30

    with pytest.raises(Retry):
        start_task()

    assert run.outputdir is None
    assert not os.path.exists(worker.OUTPUT_DIR)
    # The task goes back to the queue, so it must not be counted as processing.
    assert run.stats == []
    assert run.stopped == 0
