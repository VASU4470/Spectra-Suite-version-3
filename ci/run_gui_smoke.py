"""Run the GUI test suite without triggering fragile Qt interpreter teardown.

GitHub Actions executes the full PySide6 suite offscreen.  The unittest result can
be successful while Qt/Matplotlib crashes during Python interpreter shutdown
because process-global Qt objects are destroyed after the test runner returns.
This wrapper records the real unittest result, closes remaining top-level
widgets, processes deferred Qt events, and exits immediately with that result.
"""

from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "QtAgg")


def main() -> int:
    suite = unittest.defaultTestLoader.discover("tests")
    result = unittest.TextTestRunner(verbosity=2).run(suite)

    # Import only after discovery so test modules keep control of QApplication
    # setup exactly as they do today.
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None:
        for widget in list(QApplication.topLevelWidgets()):
            if hasattr(widget, "_skip_close_prompt"):
                widget._skip_close_prompt = True
            widget.close()
            widget.deleteLater()
        app.processEvents()
        app.quit()
        app.processEvents()

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    # Avoid the interpreter-finalization path that is crashing Qt after all
    # tests have already completed successfully on CI.
    os._exit(code)
