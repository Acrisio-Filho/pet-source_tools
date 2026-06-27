import sys
import subprocess

try:
    import PIL
except ImportError:
    python_exe = sys.executable
    subprocess.check_call([python_exe, "-m", "ensurepip"])
    subprocess.check_call([python_exe, "-m", "pip", "install", "Pillow"])