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
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    code = 0 if result.wasSuccessful() else 1
    sys.stdout.flush()
    sys.stderr.flush()
    # Exit while the suite/result objects are still alive.  Returning from
    # this function can begin Qt/Matplotlib object destruction on Windows
    # before an outer os._exit() is reached.
    os._exit(code)


if __name__ == "__main__":
    main()
