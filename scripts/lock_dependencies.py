"""Freeze the verified isolated environment, retaining Windows-only markers."""

import subprocess
import sys
from pathlib import Path

DEV = {"pytest", "ruff", "playwright", "pyee", "iniconfig", "pluggy", "pygments"}


def main():
    lines = subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True).splitlines()
    runtime, dev = [], []
    for line in lines:
        name = line.split("==")[0].lower()
        if "==" not in line:
            raise SystemExit(
                "Lock generation requires a clean environment with versioned distributions"
            )
        if name == "pywin32":
            line += '; sys_platform == "win32"'
        (dev if name in DEV else runtime).append(line)
    Path("requirements.lock").write_text(
        "# Runtime lock; generated from a verified isolated Python 3.11 environment.\n"
        + "\n".join(runtime)
        + "\n",
        encoding="utf-8",
    )
    Path("requirements-dev.lock").write_text(
        "-r requirements.lock\n" + "\n".join(dev) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
