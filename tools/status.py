import sys
from contextlib import contextmanager


@contextmanager
def status(message):
    print(f"[·] {message}", end="")
    sys.stdout.flush()
    try:
        yield
    except:  # noqa: E722
        print(f"\r[✗] {message}")
        raise
    else:
        print(f"\r[✓] {message}")
