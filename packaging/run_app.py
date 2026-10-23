"""Punto de entrada para PyInstaller: arranca la app como paquete (imports absolutos)."""
import sys

from overpower_cams.app import main

if __name__ == "__main__":
    if "--prepare-demo" in sys.argv[1:]:
        from overpower_cams.demo import main as demo_main
        sys.exit(demo_main())
    sys.exit(main())
