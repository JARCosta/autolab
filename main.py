"""
AutoLab - Local development entrypoint.

In production each module runs in its own docker-compose service via
``python -m app.runtime.entrypoint <service>``. This shim is kept for local
runs (`python main.py`) and is equivalent to ``... entrypoint all`` — it spins
up every module enabled in ``data/modules.json`` in a single process.
"""
from app.runtime.entrypoint import main

if __name__ == "__main__":
    raise SystemExit(main(["all"]))
