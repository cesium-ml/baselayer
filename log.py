from collections.abc import Callable
from datetime import datetime

ESC = "\x1b["
RESET = f"{ESC}0m"

COLOR_TABLE = [
    "black",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
    "default",
]


def __colorize(
    string: str,
    foreground: str | None = None,
    background: str | None = None,
    bold: bool = False,
    dim: bool = False,
    italic: bool = False,
    underline: bool = False,
    blinking: bool = False,
    invert: bool = False,
    invisible: bool = False,
    strikethrough: bool = False,
) -> str:
    """Wraps a string with ANSI color escape sequences corresponding to the
    style parameters given.

    All of the color and style parameters are optional.

    This function is from Robert Kern's grin:

      https://github.com/cpcloud/grin

    Copyright (c) 2007, Enthought, Inc. under a BSD license.
    """
    style_fragments: list[int] = []

    # Foreground colors go from 30-39
    if foreground in COLOR_TABLE:
        style_fragments.append(COLOR_TABLE.index(foreground) + 30)

    # Background colors go from 40-49
    if background in COLOR_TABLE:
        style_fragments.append(COLOR_TABLE.index(background) + 40)

    if bold:
        style_fragments.append(1)
    if dim:
        style_fragments.append(2)
    if italic:
        style_fragments.append(3)
    if underline:
        style_fragments.append(4)
    if blinking:
        style_fragments.append(5)
    if invert:
        style_fragments.append(7)
    if invisible:
        style_fragments.append(8)
    if strikethrough:
        style_fragments.append(9)

    styles = ";".join(map(str, style_fragments)) + "m"
    return f"{ESC}{styles}{string}{RESET}" if styles else string


def make_log(appName: str) -> Callable[[str], None]:
    app_color_table = ["red", "green", "yellow", "blue", "magenta", "cyan", "white"]
    color = app_color_table[hash(appName.encode("ascii")) % len(app_color_table)]

    return lambda message: print(
        __colorize(
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {appName}] {message}",
            foreground=color,
            bold=True,
        )
    )
