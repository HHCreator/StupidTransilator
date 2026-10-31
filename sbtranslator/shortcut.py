"""A desktop shortcut that opens the overlay window (Windows only).

    from sbtranslator import shortcut
    shortcut.create()   # SBtranslator.lnk on the desktop, opening this exe (or overlay.py)
    shortcut.state()    # ("here" | "elsewhere" | "missing", what the shortcut opens)

The overlay offers it the first time the exe starts, and its ⚙ window has a button for it.

The shortcut is made with Windows' own shell link object (IShellLinkW, what Explorer's
"Create shortcut" uses), called through ctypes: no extra packages, and no other program
started to do it (an exe that starts PowerShell looks suspicious to antivirus programs,
see build_exe.py).

How a COM object is called from ctypes: CoCreateInstance gives a pointer to the object,
whose first field points to its table of methods (the "vtable"). Method number N of an
interface is entry N of that table, counting the three methods every COM object has
first (QueryInterface, AddRef, Release); the numbers below are the methods' positions in
Windows' header files (IShellLinkW in ShObjIdl_core.h, IPersistFile in ObjIdl.h).
"""

import ctypes
import os
import sys

NAME = "SBtranslator"  # the shortcut's name on the desktop
DESCRIPTION = "SBtranslator：把英文翻成很蠢的中文"  # its tooltip

# COM ids of the shell link object and of the two interfaces used here
CLSID_SHELL_LINK = "{00021401-0000-0000-C000-000000000046}"
IID_SHELL_LINK_W = "{000214F9-0000-0000-C000-000000000046}"
IID_PERSIST_FILE = "{0000010B-0000-0000-C000-000000000046}"
CLSCTX_INPROC_SERVER = 0x1  # the object lives in this program
CSIDL_DESKTOPDIRECTORY = 0x10  # the desktop folder on disk (also when OneDrive moved it)
STGM_READ = 0x0

# Method numbers (vtable positions)
QUERY_INTERFACE, RELEASE = 0, 2  # every COM object
GET_PATH, SET_DESCRIPTION, SET_WORKING_DIRECTORY = 3, 7, 9  # IShellLinkW
GET_ARGUMENTS, SET_ARGUMENTS, SET_ICON_LOCATION, SET_PATH = 10, 11, 17, 20
LOAD, SAVE = 5, 6  # IPersistFile

LONG_PATH = 32768  # the longest path Windows allows, in characters


def available():
    """Shortcuts can only be made on Windows."""
    return os.name == "nt"


def desktop_folder():
    """The desktop folder of this user (wherever OneDrive or an admin moved it)."""
    found = ctypes.create_unicode_buffer(260)
    if ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_DESKTOPDIRECTORY, None, 0, found) == 0:
        return found.value
    return os.path.join(os.path.expanduser("~"), "Desktop")


def shortcut_file():
    """Where the desktop shortcut is: ...\\Desktop\\SBtranslator.lnk."""
    return os.path.join(desktop_folder(), NAME + ".lnk")


def launch_command():
    """What the shortcut runs: (program, arguments, folder to start in, file with the icon)."""
    if getattr(sys, "frozen", False):  # the exe (build_exe.py)
        return sys.executable, "", os.path.dirname(sys.executable), sys.executable
    # From source: pythonw.exe (Python without a console window) runs overlay.py
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    program = pythonw if os.path.exists(pythonw) else sys.executable
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(root, "overlay.py")
    if os.path.exists(script):
        return program, f'"{script}"', root, program
    return program, "-m sbtranslator.overlay", os.path.expanduser("~"), program  # pip install


# -- calling COM through ctypes ------------------------------------------------------------

class _GUID(ctypes.Structure):
    """A COM id, the way Windows keeps it in memory."""
    _fields_ = [("data1", ctypes.c_ulong), ("data2", ctypes.c_ushort),
                ("data3", ctypes.c_ushort), ("data4", ctypes.c_ubyte * 8)]


def _guid(text):
    guid = _GUID()
    ctypes.oledll.ole32.CLSIDFromString(text, ctypes.byref(guid))
    return guid


def _method(obj, number, *argtypes, result=None):
    """Method `number` of the COM object obj (a ctypes.c_void_p), as a function of its other
    arguments. It returns an HRESULT unless result says otherwise; a failed one raises
    OSError. (ctypes.HRESULT only exists on Windows, so it can't be the default here.)"""
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    prototype = ctypes.WINFUNCTYPE(result or ctypes.HRESULT, ctypes.c_void_p, *argtypes)
    function = prototype(vtable[number])
    return lambda *args: function(obj, *args)


def _with_link(work):
    """Make a shell link object, call work(link, persist_file) with it and its IPersistFile
    interface, release both and return what work returned. Raises OSError on failure."""
    # COM must be started in this thread first; S_OK (0) or S_FALSE (1, already started)
    # mean this call has to be undone at the end
    started = ctypes.windll.ole32.CoInitialize(None) in (0, 1)
    link, persist = ctypes.c_void_p(), ctypes.c_void_p()
    try:
        ctypes.oledll.ole32.CoCreateInstance(
            ctypes.byref(_guid(CLSID_SHELL_LINK)), None, CLSCTX_INPROC_SERVER,
            ctypes.byref(_guid(IID_SHELL_LINK_W)), ctypes.byref(link))
        _method(link, QUERY_INTERFACE, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))(
            ctypes.byref(_guid(IID_PERSIST_FILE)), ctypes.byref(persist))
        return work(link, persist)
    finally:
        for obj in (persist, link):
            if obj.value:
                _method(obj, RELEASE, result=ctypes.c_ulong)()
        if started:
            ctypes.windll.ole32.CoUninitialize()


# -- the shortcut ----------------------------------------------------------------------------

def create(path=None):
    """Make the desktop shortcut (or path) open this program, replacing an old one.
    Returns the shortcut's file. Raises OSError when Windows refuses."""
    path = path or shortcut_file()
    program, arguments, folder, icon = launch_command()

    def work(link, persist):
        _method(link, SET_PATH, ctypes.c_wchar_p)(program)
        _method(link, SET_ARGUMENTS, ctypes.c_wchar_p)(arguments)
        _method(link, SET_WORKING_DIRECTORY, ctypes.c_wchar_p)(folder)
        _method(link, SET_DESCRIPTION, ctypes.c_wchar_p)(DESCRIPTION)
        _method(link, SET_ICON_LOCATION, ctypes.c_wchar_p, ctypes.c_int)(icon, 0)
        _method(persist, SAVE, ctypes.c_wchar_p, ctypes.c_int)(path, 1)

    _with_link(work)
    return path


def read(path=None):
    """What a shortcut opens: (program, arguments), or None when there is no such file."""
    path = path or shortcut_file()
    if not os.path.exists(path):
        return None

    def work(link, persist):
        _method(persist, LOAD, ctypes.c_wchar_p, ctypes.c_ulong)(path, STGM_READ)
        program = ctypes.create_unicode_buffer(LONG_PATH)
        _method(link, GET_PATH, ctypes.c_wchar_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong)(
            program, LONG_PATH, None, 0)
        arguments = ctypes.create_unicode_buffer(LONG_PATH)
        _method(link, GET_ARGUMENTS, ctypes.c_wchar_p, ctypes.c_int)(arguments, LONG_PATH)
        return program.value, arguments.value

    return _with_link(work)


def _same_file(a, b):
    return bool(a and b) and os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def state(path=None):
    """Whether the desktop shortcut (or path) opens this program: ("here", program),
    ("elsewhere", the program it opens: an old copy, say) or ("missing", None)."""
    try:
        found = read(path)
    except OSError:
        return "elsewhere", None  # a file Windows can't read as a shortcut
    if found is None:
        return "missing", None
    program, arguments, *_ = launch_command()
    here = _same_file(found[0], program) and found[1].strip() == arguments.strip()
    return ("here" if here else "elsewhere"), found[0]
