# JTCS ERP — Gunicorn (production WSGI)
# Used by systemd unit jtcs-erp.service
import os

# Bind early so health checks can reach the port while workers warm up.
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")
# Keep workers modest — torch/OCR makes each worker heavy.
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
worker_class = "gthread"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "180"))
graceful_timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
capture_output = True
# False = master binds immediately; workers load Flask/torch afterward.
preload_app = False
raw_env = [
    "PYTHONUNBUFFERED=1",
]
