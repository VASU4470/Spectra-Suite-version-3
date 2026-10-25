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


def main() -> int:
    suite = unittest.defaultTestLoader.discover("tests")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    # The normal interpreter-finalization path can crash Qt/Matplotlib after
    # the suite has already completed successfully.  Exit immediately with the
    # actual unittest result instead of running process-global Qt destructors.
    os._exit(code)
