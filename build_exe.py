"""Build the standalone overlay program: dist/SBtranslator-windows.zip

    py build_exe.py

Needs PyInstaller (py -m pip install pyinstaller). The zip holds a folder with
SBtranslator.exe, Python and the data files, so it runs on a PC without Python installed:
unzip it and run SBtranslator.exe inside.

The exe also comes with the memes MemeLearnerBot has learned by then (its memes.json and
nicknames.txt, from the bot's folder on this computer or else from GitHub), so it can use
them before it has downloaded newer ones, or without internet (see bot_memes.py). Their
English cues are sbtranslator/data/meme_cues.json, which is packed with the other data.

Why a folder in a zip and not one exe: a one-file PyInstaller exe unpacks Python into a temp
folder and runs it from there, which is what a lot of malware does, so Windows Defender and
browsers often flag it as a virus (a false positive). A folder build doesn't unpack anything,
and the exe also carries version info (publisher, product name) and isn't packed with UPX,
which antivirus programs also treat as suspicious.

The GitHub build (.github/workflows/build-exe.yml) also compiles PyInstaller's bootloader
itself, which also helps. To do that here too (needs Visual Studio Build Tools with C++):

    set PYINSTALLER_COMPILE_BOOTLOADER=1
    py -m pip install --force-reinstall --no-binary pyinstaller pyinstaller
"""

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "sbtranslator", "data")
DIST = os.path.join(ROOT, "dist")
BUILD = os.path.join(ROOT, "build")
BOT = os.path.join(BUILD, "bot")  # the meme bot's files, packed as sbtranslator/data/bot
NAME = "SBtranslator"

# Shown in the exe's Properties > Details; antivirus programs trust an exe with this more
VERSION_INFO = """\
VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'HHCreator'),
      StringStruct('FileDescription', 'SBtranslator overlay: English to Chinese, stupidly'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', 'SBtranslator'),
      StringStruct('LegalCopyright', 'See LICENSE'),
      StringStruct('OriginalFilename', 'SBtranslator.exe'),
      StringStruct('ProductName', 'SBtranslator'),
      StringStruct('ProductVersion', '{version}'),
    ])]),
    VarFileInfo([VarStruct('Translation', [0x0409, 1200])]),
  ],
)
"""


def version():
    """The package version from sbtranslator/__init__.py, like "0.1.0"."""
    with open(os.path.join(ROOT, "sbtranslator", "__init__.py"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("__version__"):
                return line.split("=")[1].strip().strip("\"'")
    return "0.0.0"


def write_version_file():
    v = version()
    nums = tuple((int(p) for p in (v.split(".") + ["0"] * 4)[:4]))
    path = os.path.join(BUILD, "version_info.txt")
    os.makedirs(BUILD, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(VERSION_INFO.format(nums=nums, version=v))
    return path


def bundle_bot_memes():
    """Put the meme bot's files into BOT for the exe to come with. Returns the --add-data
    arguments for PyInstaller, or none when the files can't be had (then the exe downloads
    them from GitHub when it first translates)."""
    sys.path.insert(0, ROOT)
    from sbtranslator import bot_memes
    shutil.rmtree(BOT, ignore_errors=True)  # never an old build's files
    try:
        where = bot_memes.bundle(BOT)
    except (OSError, ValueError) as error:
        print(f"Warning: the exe comes without the meme bot's memes ({error})")
        return []
    with open(os.path.join(BOT, "memes.json"), encoding="utf-8-sig") as f:
        count = len(bot_memes.parse_memes(f.read()))
    print(f"Packing the meme bot's {count} memes, from {where}")
    return ["--add-data", f"{BOT}{os.pathsep}sbtranslator/data/bot"]


def main():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        sys.exit("PyInstaller is missing. Install it with: py -m pip install pyinstaller")
    subprocess.run(
        [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm", "--clean",
            "--onedir", "--windowed",  # a folder (not a self-unpacking exe), no console window
            "--noupx",
            "--name", NAME,
            "--version-file", write_version_file(),
            # Pack the data folder at sbtranslator/data, where the code looks
            "--add-data", f"{DATA}{os.pathsep}sbtranslator/data",
            *bundle_bot_memes(),
            "--distpath", DIST,
            "--workpath", os.path.join(BUILD, "pyinstaller"),
            "--specpath", BUILD,
            os.path.join(ROOT, "overlay.py"),  # the script the exe runs: the overlay window
        ],
        check=True,
        cwd=ROOT,
    )
    # Zip the folder so it downloads as one file: dist/SBtranslator-windows.zip
    zip_path = shutil.make_archive(os.path.join(DIST, f"{NAME}-windows"), "zip", DIST, NAME)
    print(f"\nBuilt {os.path.join(DIST, NAME, NAME + '.exe')}\nZipped {zip_path}")


if __name__ == "__main__":
    main()
