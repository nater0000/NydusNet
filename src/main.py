import multiprocessing
import ctypes
from ctypes import c_int, c_wchar, c_wchar_p

# --- MONKEYPATCH FOR ANSIBLE ON WINDOWS (MUST BE AT THE TOP) ---

# 1. Patch for multiprocessing
_original_get_context = multiprocessing.get_context
def _patched_get_context(method):
    if method == 'fork':
        return _original_get_context('spawn')
    return _original_get_context(method)
multiprocessing.get_context = _patched_get_context

# 2. Patch for ctypes LoadLibrary(None)
_original_cdll_load_library = ctypes.cdll.LoadLibrary
def _patched_cdll_load_library(name):
    if name is None:
        return ctypes.cdll.msvcrt
    return _original_cdll_load_library(name)
ctypes.cdll.LoadLibrary = _patched_cdll_load_library

# 3. Patch for missing 'wcwidth' and 'wcswidth' C functions
try:
    from wcwidth import wcwidth, wcswidth
    
    # Patch for single character width
    WCWIDTH_PROTOTYPE = ctypes.CFUNCTYPE(c_int, c_wchar)
    wcwidth_func = WCWIDTH_PROTOTYPE(wcwidth)
    ctypes.cdll.msvcrt.wcwidth = wcwidth_func
    
    # Patch for string width
    WCSWIDTH_PROTOTYPE = ctypes.CFUNCTYPE(c_int, c_wchar_p)
    wcswidth_func = WCSWIDTH_PROTOTYPE(wcswidth)
    ctypes.cdll.msvcrt.wcswidth = wcswidth_func

except ImportError:
    pass

# --- END MONKEYPATCH ---


# Now that the patches are in place, we can safely import the rest of the application
import customtkinter as ctk
from app import App
from utils.logger import setup_logger


def main():
    """
    Main function to initialize and run the NydusNet application.
    """
    setup_logger()
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()

if __name__ == "__main__":
    multiprocessing.set_start_method('spawn')
    main()