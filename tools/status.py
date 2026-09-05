import io
import sys
from contextlib import contextmanager


@contextmanager
def redirect_stdout(out):
    """Temporarily redirect stdout to `out`."""
    sys.stdout.flush()
    stdout = sys.stdout
    try:
        sys.stdout = out
        yield
    finally:
        sys.stdout = stdout


@contextmanager
def status(message, quiet=False):
    """Print a progress line, resolved to [✓] or [✗] when the block finishes.

    With `quiet`, the block's stdout is captured and replayed only if it
    raises, so a run of steps stays one line each until something fails.
    """
    print(f"[·] {message}", end="")
    sys.stdout.flush()

    captured = io.StringIO() if quiet else None

    try:
        if captured is None:
            yield
        else:
            with redirect_stdout(captured):
                yield
    except:  # noqa: E722
        print(f"\r[✗] {message}")
        # stdout is restored by now, so this reaches the real terminal
        output = captured.getvalue().strip() if captured else ""
        if output:
            print("-- captured output --")
            print(output)
            print("-- end output --")
        raise
    else:
        print(f"\r[✓] {message}")
