"""Small tracked-file credential regression check; not a comprehensive secret scanner."""

import re
import subprocess
from pathlib import Path

PATTERNS = [
    r"\bgsk_[A-Za-z0-9]{25,}\b",
    r"\bAIza[A-Za-z0-9_-]{25,}\b",
    r"\bgithub_pat_[A-Za-z0-9_]{30,}\b",
    r"\bghp_[A-Za-z0-9]{25,}\b",
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
]


def main():
    names = subprocess.check_output(["git", "ls-files", "-z"], text=True).split("\x00")
    failures = []
    for name in filter(None, names):
        path = Path(name)
        if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
            failures.append(name)
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            if any(re.search(pattern, text) for pattern in PATTERNS):
                failures.append(name)
    if failures:
        print("Potential credential material in tracked files:", ", ".join(sorted(set(failures))))
        raise SystemExit(1)
    print("PASS: tracked environment-file and known credential-pattern checks")


if __name__ == "__main__":
    main()
