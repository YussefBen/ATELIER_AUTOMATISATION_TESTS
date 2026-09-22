"""Point d'entrée de la tâche planifiée PythonAnywhere (Tasks > Scheduled tasks)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import storage  # noqa: E402
from tester.runner import run_all  # noqa: E402

if __name__ == "__main__":
    storage.init_db()
    run = run_all(trigger="scheduled")
    run_id = storage.save_run(run)
    s = run["summary"]
    print(f"Run #{run_id} {run['timestamp']} : {s['passed']}/{s['total']} OK, "
          f"p95 {s['latency_ms_p95']} ms, dispo {round(s['availability'] * 100)} %")
