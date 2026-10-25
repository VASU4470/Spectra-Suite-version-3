"""Run the GUI test suite without triggering fragile Qt interpreter teardown.

GitHub Actions executes the full PySide6 suite offscreen.  The unittest result can
be successful while Qt/Matplotlib crashes during Python interpreter shutdown
because process-global Qt objects are destroyed after the test runner returns.
This wrapper records the real unittest result, closes remaining top-level
widgets, processes deferred Qt events, and exits immediately with that result.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "QtAgg")


def main() -> None:
    suite = unittest.defaultTestLoader.discover("tests")
    stream = unittest.runner._WritelnDecorator(sys.stderr)
    result = unittest.TextTestResult(stream, descriptions=True, verbosity=2)
    result.startTestRun()
    started = __import__("time").perf_counter()
    try:
        suite(result)
    finally:
        result.stopTestRun()
    elapsed = __import__("time").perf_counter() - started

    stream.writeln()
    stream.writeln("-" * 70)
    run = result.testsRun
    stream.writeln(f"Ran {run} test{'s' if run != 1 else ''} in {elapsed:.3f}s")
    stream.writeln()
    if result.wasSuccessful():
        stream.writeln("OK")
        code = 0
    else:
        details = []
        if result.failures:
            details.append(f"failures={len(result.failures)}")
        if result.errors:
            details.append(f"errors={len(result.errors)}")
        if result.skipped:
            details.append(f"skipped={len(result.skipped)}")
        stream.writeln("FAILED" + (f" ({', '.join(details)})" if details else ""))
        code = 1

    sys.stdout.flush()
    sys.stderr.flush()
    # Do not return through Python/Qt teardown. On Windows, a Qt-loaded
    # process has been observed to turn os._exit(0) into exit code 1 in CI, so
    # use the operating-system process exit directly. POSIX uses os._exit.
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.ExitProcess(code)
    os._exit(code)


if __name__ == "__main__":
    main()
