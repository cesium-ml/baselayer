from datetime import datetime
import zlib


BOLD = "\033[1m"
NORMAL = "\033[0;0m"


COLOR_TABLE = ['black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan',
               'white', 'default']


def colorize(s, fg=None, bg=None, bold=False, underline=False, reverse=False):
    """Wraps a string with ANSI color escape sequences corresponding to the
    style parameters given.

    All of the color and style parameters are optional.

    This function is from Robert Kern's grin:

      https://github.com/cpcloud/grin

    Copyright (c) 2007, Enthought, Inc. under a BSD license.

    Parameters
    ----------
    s : str
    fg : str
        Foreground color of the text.  One of (black, red, green, yellow, blue,
        magenta, cyan, white, default)
    bg : str
        Background color of the text.  Color choices are the same as for fg.
    bold : bool
        Whether or not to display the text in bold.
    underline : bool
        Whether or not to underline the text.
    reverse : bool
        Whether or not to show the text in reverse video.

    Returns
    -------
    A string with embedded color escape sequences.
    """

    style_fragments = []
    if fg in COLOR_TABLE:
        # Foreground colors go from 30-39
        style_fragments.append(COLOR_TABLE.index(fg) + 30)
    if bg in COLOR_TABLE:
        # Background colors go from 40-49
        style_fragments.append(COLOR_TABLE.index(bg) + 40)
    if bold:
        style_fragments.append(1)
    if underline:
        style_fragments.append(4)
    if reverse:
        style_fragments.append(7)
    style_start = '\x1b[' + ';'.join(map(str, style_fragments)) + 'm'
    style_end = '\x1b[0m'
    return style_start + s + style_end


def log(app, message):
    color = COLOR_TABLE[zlib.crc32(message.encode('ascii')) % len(COLOR_TABLE)]
    timestamp = datetime.now().strftime('%H:%M:%S')
    formatted_message = f'[{timestamp} {app}] {message}'
    print(colorize(formatted_message, fg=color, bold=True))


def make_log(app):
    def app_log(*args, **kwargs):
        log(app, *args, **kwargs)

    return app_log
