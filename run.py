"""Start the BOE viewer:  python run.py [--port 8765]   (open http://127.0.0.1:8765)"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from boe.web.server import main  # noqa: E402

if __name__ == "__main__":
    main()
