"""Tests "as code" de l'API Frankfurter.

Chaque test reçoit le client, lève AssertionError en cas d'échec (FAIL)
et peut renvoyer un court message de détail en cas de succès.
Toute autre exception (réseau, budget dépassé...) est comptée en ERROR.
"""
import math
import re
from datetime import date

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LATENCY_SAMPLES = 5
P95_THRESHOLD_MS = 1500


def expect(condition, message):
    if not condition:
        raise AssertionError(message)


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def call(client, path, params=None):
    response = client.get(path, params)
    if response.error:
        raise ConnectionError(f"Aucune réponse : {response.error}")
    return response


# ---------- A. Tests de contrat ----------

def test_latest_status_200(client):
    r = call(client, "/latest", {"from": "EUR"})
    expect(r.status == 200, f"HTTP {r.status} reçu, 200 attendu")
    return "HTTP 200"


def test_latest_content_type_json(client):
    r = call(client, "/latest", {"from": "EUR"})
    expect("application/json" in r.content_type, f"Content-Type inattendu : {r.content_type!r}")
    expect(isinstance(r.json, dict), "Le corps de la réponse n'est pas un objet JSON")
    return r.content_type


def test_latest_required_fields(client):
    r = call(client, "/latest", {"from": "EUR"})
    expect(isinstance(r.json, dict), "Réponse non JSON")
    missing = [f for f in ("amount", "base", "date", "rates") if f not in r.json]
    expect(not missing, f"Champs manquants : {', '.join(missing)}")
    return "amount, base, date, rates présents"


def test_latest_field_types(client):
    r = call(client, "/latest", {"from": "EUR"})
    body = r.json
    expect(isinstance(body, dict), "Réponse non JSON")
    expect(is_number(body.get("amount")), "amount doit être un nombre")
    expect(isinstance(body.get("base"), str) and len(body["base"]) == 3, "base doit être un code devise de 3 lettres")
    expect(isinstance(body.get("date"), str) and DATE_RE.match(body["date"]), "date doit être au format AAAA-MM-JJ")
    date.fromisoformat(body["date"])  # lève ValueError si la date est invalide
    rates = body.get("rates")
    expect(isinstance(rates, dict) and rates, "rates doit être un objet non vide")
    bad = [k for k, v in rates.items() if not (isinstance(k, str) and len(k) == 3 and is_number(v) and v > 0)]
    expect(not bad, f"Taux invalides pour : {', '.join(bad[:5])}")
    return f"{len(rates)} taux valides"


def test_latest_filter_currencies(client):
    r = call(client, "/latest", {"from": "USD", "to": "EUR,GBP"})
    expect(r.status == 200, f"HTTP {r.status} reçu, 200 attendu")
    expect(r.json.get("base") == "USD", f"base {r.json.get('base')!r} au lieu de 'USD'")
    expect(set(r.json.get("rates", {})) == {"EUR", "GBP"}, f"Devises renvoyées : {sorted(r.json.get('rates', {}))}")
    return "Filtre to=EUR,GBP respecté"


def test_amount_conversion(client):
    r = call(client, "/latest", {"amount": 10, "from": "EUR", "to": "USD"})
    expect(r.status == 200, f"HTTP {r.status} reçu, 200 attendu")
    expect(r.json.get("amount") == 10, f"amount {r.json.get('amount')!r} au lieu de 10")
    expect(is_number(r.json.get("rates", {}).get("USD")), "Montant converti en USD absent")
    return f"10 EUR = {r.json['rates']['USD']} USD"


def test_currencies_list(client):
    r = call(client, "/currencies")
    expect(r.status == 200, f"HTTP {r.status} reçu, 200 attendu")
    body = r.json
    expect(isinstance(body, dict) and body, "La liste des devises doit être un objet non vide")
    expect("EUR" in body and "USD" in body, "EUR et USD doivent figurer dans la liste")
    expect(all(isinstance(v, str) for v in body.values()), "Chaque devise doit avoir un libellé texte")
    return f"{len(body)} devises"


def test_historical_date(client):
    r = call(client, "/2024-01-02", {"from": "EUR"})
    expect(r.status == 200, f"HTTP {r.status} reçu, 200 attendu")
    expect(r.json.get("date") == "2024-01-02", f"date {r.json.get('date')!r} au lieu de '2024-01-02'")
    expect(r.json.get("base") == "EUR", "base doit valoir EUR")
    return "Historique du 2024-01-02 cohérent"


def test_invalid_currency_rejected(client):
    r = call(client, "/latest", {"from": "XXX"})
    expect(r.status in (400, 404, 422), f"HTTP {r.status} reçu, une erreur 4xx était attendue")
    return f"Devise invalide rejetée (HTTP {r.status})"


# ---------- B. QoS ----------

def test_latency_p95(client):
    latencies = []
    for _ in range(LATENCY_SAMPLES):
        r = call(client, "/latest", {"from": "EUR", "to": "USD"})
        expect(r.status == 200, f"HTTP {r.status} pendant l'échantillonnage")
        latencies.append(r.latency_ms)
    latencies.sort()
    p95 = latencies[math.ceil(0.95 * len(latencies)) - 1]
    expect(p95 < P95_THRESHOLD_MS, f"p95 de {p95:.0f} ms, seuil {P95_THRESHOLD_MS} ms")
    return f"p95 {p95:.0f} ms sur {LATENCY_SAMPLES} appels"


TESTS = [
    ("GET /latest renvoie HTTP 200", test_latest_status_200),
    ("GET /latest renvoie du JSON", test_latest_content_type_json),
    ("GET /latest contient les champs obligatoires", test_latest_required_fields),
    ("GET /latest respecte les types attendus", test_latest_field_types),
    ("GET /latest filtre les devises demandées", test_latest_filter_currencies),
    ("GET /latest convertit un montant", test_amount_conversion),
    ("GET /currencies liste les devises", test_currencies_list),
    ("GET /2024-01-02 renvoie l'historique", test_historical_date),
    ("GET /latest?from=XXX est rejeté", test_invalid_currency_rejected),
    ("Latence p95 sous 1500 ms", test_latency_p95),
]
