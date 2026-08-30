#!/usr/bin/env python
import os
import sys


def _force_utf8_streams():
    """Print UTF-8 regardless of the console's legacy codepage.

    On Windows stdout defaults to the ANSI codepage (cp1252 here), which cannot
    encode Arabic. Anything that writes Arabic to the console then dies with
    UnicodeEncodeError — most visibly the console email backend, which renders
    the Arabic welcome letter to stdout and surfaced as a generic
    "check the platform mail settings" error.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure is None:  # already wrapped/redirected by the caller
            continue
        try:
            reconfigure(encoding='utf-8', errors='backslashreplace')
        except (ValueError, OSError):
            pass


if __name__ == '__main__':
    _force_utf8_streams()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
