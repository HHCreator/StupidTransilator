"""Command line entry point, kept so `py translator.py "Hello"` still works.

The code lives in the sbtranslator package; see sbtranslator/translator.py.
"""

from sbtranslator.translator import main

if __name__ == "__main__":
    main()
