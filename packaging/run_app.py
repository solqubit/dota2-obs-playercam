"""Punto de entrada para PyInstaller: arranca la app como paquete (imports absolutos)."""
import sys

from overpower_cams.app import main

if __name__ == "__main__":
    sys.exit(main())
