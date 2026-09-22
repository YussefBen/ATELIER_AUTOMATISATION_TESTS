import json
import sqlite3
import time

from flask import Flask, Response, jsonify, redirect, render_template, url_for

import storage
from tester.runner import run_all

app = Flask(__name__)
app.json.ensure_ascii = False

MIN_INTERVAL_S = 300  # anti-spam : 1 run toutes les 5 minutes maximum

storage.init_db()


@app.route("/")
def index():
    return redirect(url_for("dashboard"))


@app.route("/run", methods=["GET", "POST"])
def run():
    last = storage.get_last_run()
    if last:
        elapsed = time.time() - last["created_at"]
        if elapsed < MIN_INTERVAL_S:
            return jsonify({
                "status": "skipped",
                "reason": "Anti-spam : 1 run toutes les 5 minutes maximum",
                "retry_in_s": int(MIN_INTERVAL_S - elapsed),
            }), 429

    result = run_all(trigger="manual")
    result["id"] = storage.save_run(result)
    return jsonify(result)


@app.route("/dashboard")
def dashboard():
    runs = storage.list_runs(limit=50)
    chronological = list(reversed(runs))
    chart = {
        "labels": [r["timestamp"][5:16].replace("T", " ") for r in chronological],
        "avg": [r["summary"]["latency_ms_avg"] for r in chronological],
        "p95": [r["summary"]["latency_ms_p95"] for r in chronological],
    }
    return render_template(
        "dashboard.html",
        last=runs[0] if runs else None,
        runs=runs,
        chart=chart,
    )


@app.route("/health")
def health():
    try:
        last = storage.get_last_run()
        total = storage.count_runs()
    except sqlite3.Error as exc:
        return jsonify({"status": "error", "database": str(exc)}), 503

    body = {"status": "ok", "database": "ok", "api": "Frankfurter", "runs_stored": total}
    if last:
        body.update({
            "last_run": last["timestamp"],
            "last_run_age_s": int(time.time() - last["created_at"]),
            "last_verdict": last["summary"]["verdict"],
            "last_availability": last["summary"]["availability"],
        })
    else:
        body["last_run"] = None
    return jsonify(body)


@app.route("/export.json")
def export_json():
    runs = storage.list_runs(limit=None)
    return Response(
        json.dumps(runs, ensure_ascii=False, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=runs_frankfurter.json"},
    )
