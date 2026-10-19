"""Compatibilidad: la comprobación vigente utiliza la aplicación y el contrato por orden."""
import sys
from worksheet_ui_fixture import main

if __name__ == "__main__":
    if "--verify-only" not in sys.argv: sys.argv.append("--verify-only")
    main()
