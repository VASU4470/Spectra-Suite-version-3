"""Stable cross-platform runner for the PySide6 GUI smoke suite.

The GUI tests themselves are authoritative. On Windows/macOS, Qt/Matplotlib can
crash during interpreter teardown after unittest has completed successfully.
To avoid turning that teardown defect into a false test failure, this module
uses a non-Qt parent process and a worker process:

1. the worker runs the normal unittest suite;
2. its TestResult writes an atomic result marker from stopTestRun(), after the
   complete suite has finished;
3. the parent trusts only that marker, not a later Qt interpreter exit code.

Actual test failures/errors still make the CI step fail.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
MARKER = Path(tempfile.gettempdir()) / "spectrasuite-gui-smoke-result.json"


class MarkerResult(unittest.TextTestResult):
    """Persist the completed unittest result before Qt interpreter teardown."""

    def stopTestRun(self):
        super().stopTestRun()
        payload = {
            "success": self.wasSuccessful(),
            "tests_run": self.testsRun,
            "failures": len(self.failures),
            "errors": len(self.errors),
            "skipped": len(self.skipped),
        }
        temporary = MARKER.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(MARKER)


class MarkerRunner(unittest.TextTestRunner):
    resultclass = MarkerResult


def worker() -> int:
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("MPLBACKEND", "QtAgg")

    suite = unittest.defaultTestLoader.discover("tests")
    result = MarkerRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def parent() -> int:
    try:
        MARKER.unlink()
    except FileNotFoundError:
        pass

    command = [sys.executable, str(Path(__file__).resolve()), "--worker"]
    process = subprocess.Popen(command, cwd=ROOT)
    marker_seen = False
    while process.poll() is None:
        if MARKER.is_file():
            marker_seen = True
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                # The complete unittest result is already recorded. Any process
                # still alive here is stuck in Qt/Matplotlib interpreter teardown.
                process.kill()
                process.wait()
            break
        time.sleep(0.1)

    returncode = process.returncode if process.returncode is not None else 1

    if not MARKER.is_file():
        print(
            "GUI smoke worker did not record a completed unittest result; "
            f"worker exit code was {returncode}.",
            file=sys.stderr,
        )
        return returncode or 1

    try:
        payload = json.loads(MARKER.read_text(encoding="utf-8"))
    finally:
        try:
            MARKER.unlink()
        except FileNotFoundError:
            pass

    tests_run = int(payload.get("tests_run", 0))
    success = bool(payload.get("success", False))
    if not success:
        print(
            "GUI smoke suite reported failures: "
            f"tests={tests_run}, failures={payload.get('failures', 0)}, "
            f"errors={payload.get('errors', 0)}, skipped={payload.get('skipped', 0)}.",
            file=sys.stderr,
        )
        return 1

    if returncode:
        print(
            "GUI smoke assertions passed "
            f"({tests_run} tests); ignoring post-test Qt teardown exit "
            f"{returncode}.",
            file=sys.stderr,
        )
    else:
        print(f"GUI smoke suite passed cleanly ({tests_run} tests).")

    return 0


if __name__ == "__main__":
    if "--worker" in sys.argv:
        raise SystemExit(worker())
    raise SystemExit(parent())
