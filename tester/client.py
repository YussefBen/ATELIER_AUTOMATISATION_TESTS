"""Client HTTP de test : timeout strict, 1 retry max, gestion 429/5xx, mesure de latence."""
import time
from dataclasses import dataclass, field

import requests

BASE_URL = "https://api.frankfurter.app"
TIMEOUT_S = 3              # timeout strict par requête
MAX_RETRIES = 1            # 1 retry maximum
MAX_REQUESTS_PER_RUN = 20  # anti-spam : 20 requêtes max par run
MAX_BACKOFF_S = 5          # attente max en cas de 429 / 5xx


class RequestBudgetExceeded(Exception):
    """Levée si un run dépasse le nombre de requêtes autorisé."""


@dataclass
class ApiResponse:
    status: int | None
    json: object
    headers: dict = field(default_factory=dict)
    latency_ms: float | None = None
    error: str | None = None
    retried: bool = False

    @property
    def content_type(self) -> str:
        return self.headers.get("Content-Type", "")


class ApiClient:
    def __init__(self, base_url=BASE_URL, timeout=TIMEOUT_S, max_requests=MAX_REQUESTS_PER_RUN):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_requests = max_requests
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "atelier-api-monitoring/1.0 (ybenchouchane.pythonanywhere.com)"
        # Trace de chaque requête envoyée : sert au calcul des métriques QoS
        self.calls = []

    def get(self, path, params=None) -> ApiResponse:
        attempt = 0
        while True:
            if len(self.calls) >= self.max_requests:
                raise RequestBudgetExceeded(
                    f"Budget de {self.max_requests} requêtes par run atteint"
                )

            start = time.perf_counter()
            try:
                resp = self.session.get(self.base_url + path, params=params, timeout=self.timeout)
            except requests.RequestException as exc:  # timeout, DNS, connexion refusée...
                latency = (time.perf_counter() - start) * 1000
                self._trace(path, None, latency, type(exc).__name__)
                if attempt < MAX_RETRIES:
                    attempt += 1
                    time.sleep(1)
                    continue
                return ApiResponse(None, None, {}, latency, f"{type(exc).__name__}: {exc}", attempt > 0)

            latency = (time.perf_counter() - start) * 1000
            self._trace(path, resp.status_code, latency, None)

            # 429 (rate limit) ou 5xx : on attend puis on retente une seule fois
            if (resp.status_code == 429 or resp.status_code >= 500) and attempt < MAX_RETRIES:
                attempt += 1
                time.sleep(self._backoff(resp))
                continue

            return ApiResponse(
                resp.status_code, self._parse_json(resp), dict(resp.headers), latency, None, attempt > 0
            )

    def _trace(self, path, status, latency_ms, error):
        self.calls.append({"path": path, "status": status, "latency_ms": latency_ms, "error": error})

    @staticmethod
    def _backoff(resp) -> float:
        retry_after = resp.headers.get("Retry-After", "")
        delay = int(retry_after) if retry_after.isdigit() else 1
        return min(delay, MAX_BACKOFF_S)

    @staticmethod
    def _parse_json(resp):
        try:
            return resp.json()
        except ValueError:
            return None
