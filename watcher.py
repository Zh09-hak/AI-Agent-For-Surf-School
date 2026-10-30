import os
import signal
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

import app
from integrations import db

RUNNING = True


def _stop(signum, frame):
    global RUNNING
    RUNNING = False
    print("\n🛑 Stopping after the current cycle...")


def main():
    interval = int(os.getenv("POLL_INTERVAL_SECONDS") or 60)
    once = "--once" in sys.argv

    signal.signal(signal.SIGINT, _stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _stop)

    db.init_db()
    print(f"🚀 Watcher started | interval={interval}s | mode={os.getenv('AUTO_APPROVE_MODE','shadow')}")
    print(f"🗄  DB: {db.DB_PATH}")

    while RUNNING:
        started = datetime.now()
        try:
            res = app.run_once(verbose=True)
            if res["new"]:
                db.audit("watcher", "poll_cycle", details=res)
        except Exception:
            print("💥 Loop error (continuing):")
            traceback.print_exc()
            db.audit("watcher", "cycle_error", details={"trace": traceback.format_exc()[-800:]})

        if once:
            break

        elapsed = (datetime.now() - started).total_seconds()
        time.sleep(max(1, interval - elapsed))

    print("👋 Watcher stopped")


if __name__ == "__main__":
    main()