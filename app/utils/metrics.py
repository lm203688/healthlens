"""Prometheus metrics for HealthLens"""
import time
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# --- Request Metrics ---
REQUEST_COUNT = Counter(
    "healthlens_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

REQUEST_LATENCY = Histogram(
    "healthlens_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# --- Business Metrics ---
ACTIVE_USERS = Gauge(
    "healthlens_active_users",
    "Number of active users (logged in within 24h)",
)

TOTAL_RECORDS = Gauge(
    "healthlens_total_health_records",
    "Total health records in database",
)

TOTAL_DIAGNOSES = Gauge(
    "healthlens_total_diagnoses",
    "Total diagnoses",
)

OCR_TASKS_TOTAL = Counter(
    "healthlens_ocr_tasks_total",
    "Total OCR tasks processed",
    ["status"],  # success, failure
)

OCR_TASK_DURATION = Histogram(
    "healthlens_ocr_task_duration_seconds",
    "OCR task processing duration",
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)

CELERY_TASKS_TOTAL = Counter(
    "healthlens_celery_tasks_total",
    "Total Celery tasks",
    ["task_name", "status"],
)

CELERY_QUEUE_SIZE = Gauge(
    "healthlens_celery_queue_size",
    "Current Celery queue depth",
)

# --- Database Metrics ---
DB_POOL_SIZE = Gauge(
    "healthlens_db_pool_size",
    "Database connection pool size",
)

DB_POOL_CHECKEDOUT = Gauge(
    "healthlens_db_pool_checked_out",
    "Database connections currently checked out",
)


class RequestMetricsMiddleware:
    """ASGI middleware to collect HTTP request metrics."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope["method"]
        path = scope["path"]

        # Normalize path (replace UUIDs and IDs with placeholder)
        normalized = self._normalize_path(path)

        start = time.perf_counter()
        status_code = 500  # default if something goes wrong

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start
            REQUEST_COUNT.labels(method=method, endpoint=normalized, status=str(status_code)).inc()
            REQUEST_LATENCY.labels(method=method, endpoint=normalized).observe(duration)

    @staticmethod
    def _normalize_path(path: str) -> str:
        """Replace UUIDs and numeric IDs with :param"""
        import re
        # Replace UUID patterns
        path = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', ':id', path)
        # Replace numeric IDs
        path = re.sub(r'/\d+(?=/|$)', '/:id', path)
        return path