"""Exécute la suite de tests et calcule les métriques de qualité de service."""
import math
from datetime import datetime
from zoneinfo import ZoneInfo

from tester.client import ApiClient, BASE_URL, RequestBudgetExceeded
from tester.tests import TESTS

API_NAME = "Frankfurter"
TZ = ZoneInfo("Europe/Paris")


def _p95(values):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def _verdict(availability, failed, p95):
    if availability < 0.5:
        return "down", "Le service est indisponible."
    if availability < 1 or failed > 0 or (p95 is not None and p95 > 1500):
        return "warn", "Le service répond, avec des anomalies."
    return "ok", "Le service répond normalement."


def _interpretation(avg, p95, error_rate, availability, requests_sent):
    if p95 is None:
        return "Aucune réponse exploitable : impossible de mesurer la latence."
    if p95 < 500:
        speed = "réactivité excellente"
    elif p95 < 1500:
        speed = "réactivité correcte"
    else:
        speed = "service lent"
    return (
        f"Latence moyenne de {avg} ms et p95 de {p95} ms sur {requests_sent} requêtes ({speed}). "
        f"{round(error_rate * 100)} % des tests en échec, disponibilité de {round(availability * 100)} %."
    )


def run_all(trigger="manual"):
    client = ApiClient()
    results = []

    for name, func in TESTS:
        before = len(client.calls)
        try:
            detail = func(client) or ""
            status = "PASS"
        except AssertionError as exc:
            status, detail = "FAIL", str(exc)
        except RequestBudgetExceeded as exc:
            status, detail = "ERROR", str(exc)
        except Exception as exc:  # erreur réseau, JSON inattendu...
            status, detail = "ERROR", f"{type(exc).__name__}: {exc}"

        calls = client.calls[before:]
        latency = round(sum(c["latency_ms"] for c in calls)) if calls else None
        results.append({
            "name": name,
            "status": status,
            "latency_ms": latency,
            "requests": len(calls),
            "details": detail,
        })

    passed = sum(r["status"] == "PASS" for r in results)
    failed = sum(r["status"] == "FAIL" for r in results)
    errors = sum(r["status"] == "ERROR" for r in results)
    total = len(results)

    # Métriques calculées sur toutes les requêtes HTTP envoyées pendant le run
    answered = [c for c in client.calls if c["status"] is not None]
    latencies = [c["latency_ms"] for c in answered]
    healthy = [c for c in answered if c["status"] < 500 and c["status"] != 429]
    requests_sent = len(client.calls)
    availability = len(healthy) / requests_sent if requests_sent else 0.0
    http_errors = requests_sent - len(healthy)

    avg = round(sum(latencies) / len(latencies)) if latencies else None
    p95 = round(_p95(latencies)) if latencies else None
    error_rate = (failed + errors) / total if total else 0.0
    level, verdict = _verdict(availability, failed + errors, p95)

    return {
        "api": API_NAME,
        "base_url": BASE_URL,
        "timestamp": datetime.now(TZ).isoformat(timespec="seconds"),
        "trigger": trigger,
        "summary": {
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "total": total,
            "error_rate": round(error_rate, 3),
            "latency_ms_avg": avg,
            "latency_ms_p95": p95,
            "availability": round(availability, 3),
            "http_error_rate": round(http_errors / requests_sent, 3) if requests_sent else 0.0,
            "requests": requests_sent,
            "verdict_level": level,
            "verdict": verdict,
            "interpretation": _interpretation(avg, p95, error_rate, availability, requests_sent),
        },
        "tests": results,
    }
