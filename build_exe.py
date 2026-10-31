# build_exe.py — сборка одиночного portable-exe (PyInstaller: onefile, без консоли).
# Запуск:  python build_exe.py   ->  dist\zapret-simple.exe
# Конечному пользователю не нужны ни Python, ни pip; первый запуск поднимает UAC.
import PyInstaller.__main__

PyInstaller.__main__.run([
    "--noconfirm",
    "--onefile",
    "--windowed",
    "--name", "zapret-simple",
    "--icon", "assets/app.ico",
    "--add-data", "assets;assets",
    # pywin32: SCM-модули, часть которых PyInstaller не видит статическим анализом
    "--hidden-import", "win32serviceutil",
    "--hidden-import", "win32service",
    "--hidden-import", "win32api",
    "--hidden-import", "win32con",
    "--hidden-import", "win32process",
    "--hidden-import", "win32event",
    "--hidden-import", "win32timezone",
    "--hidden-import", "pywintypes",
    "zapret_pyside.py",
])
print("OK: dist\\zapret-simple.exe")
