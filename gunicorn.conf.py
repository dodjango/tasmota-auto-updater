"""Gunicorn configuration for the Tasmota Updater.

Uses a threaded worker so slow, blocking device I/O does not exhaust processes,
and a single worker so the in-memory background-job store (app/tasmota/jobs.py)
stays consistent across the request that starts a batch and the requests that
poll it. Scaling to multiple workers would require a shared job store.
"""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '5001')}"

# One worker keeps the in-memory job registry consistent; threads provide
# concurrency for the (mostly I/O-bound) request handlers.
workers = int(os.environ.get("GUNICORN_WORKERS", "1"))
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", "8"))

# Batch updates run in a background thread and return 202 immediately, so they
# are not bound by this. A single synchronous device update can still run for
# minutes, so keep the request timeout above the maximum device timeout (600s).
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "700"))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "30"))

accesslog = "-"
errorlog = "-"
