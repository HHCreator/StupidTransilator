"""Build the standalone overlay program: dist/SBtranslator.exe

    py build_exe.py

Needs PyInstaller (py -m pip install pyinstaller). The exe is a single file that carries
Python and the data files with it, so it runs on a PC without Python installed.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "sbtranslator", "data")


def main():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        sys.exit("PyInstaller is missing. Install it with: py -m pip install pyinstaller")
    subprocess.run(
        [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm", "--clean",
            "--onefile", "--windowed",  # one file, no console window
            "--name", "SBtranslator",
            # Pack the data folder into the exe at sbtranslator/data, where the code looks
            "--add-data", f"{DATA}{os.pathsep}sbtranslator/data",
            "--distpath", os.path.join(ROOT, "dist"),
            "--workpath", os.path.join(ROOT, "build", "pyinstaller"),
            "--specpath", os.path.join(ROOT, "build"),
            os.path.join(ROOT, "overlay.py"),  # the script the exe runs: the overlay window
        ],
        check=True,
        cwd=ROOT,
    )
    print(f"\nBuilt {os.path.join(ROOT, 'dist', 'SBtranslator.exe')}")


if __name__ == "__main__":
    main()
