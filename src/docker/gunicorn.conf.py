"""Gunicorn configuration for NeuronSphere Deployment GUI."""
import multiprocessing
import os

# Server socket
bind = "0.0.0.0:8000"

# Worker processes
#
# `multiprocessing.cpu_count()` reports the HOST node's core count and ignores
# this container's cgroup CPU quota, so the usual `cpu_count() * 2 + 1` formula
# sizes the pool to the node rather than to the pod. On a 16-vCPU node that is
# 33 workers inside a 500m container -- and because every worker imports Django
# *and* builds the FastMCP server independently (deployment_gui/asgi.py, and no
# preload_app below), the pod OOMKills during startup. That is not theoretical:
# it is exactly how cloud deploys broke once the MCP server landed.
#
# So derive the default from the cgroup CPU quota, which is the container's real
# allowance, and clamp it. GUNICORN_WORKERS still takes precedence when set --
# the Helm chart emits it from `config.gunicornWorkers`.
MAX_WORKERS = 8


def _cgroup_cpus():
    """This container's CPU allowance from its cgroup quota, or None if unset.

    Returns a float (0.5 for a `cpu: 500m` limit). None means the cgroup imposes
    no quota, in which case the caller falls back to the host core count.
    """
    try:
        # cgroup v2: "<quota> <period>", or "max <period>" when unconstrained.
        with open("/sys/fs/cgroup/cpu.max") as f:
            quota_raw, period_raw = f.read().split()
        if quota_raw == "max":
            return None
        quota, period = int(quota_raw), int(period_raw)
    except (OSError, ValueError):
        try:
            # cgroup v1: quota is -1 when unconstrained.
            with open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us") as f:
                quota = int(f.read())
            with open("/sys/fs/cgroup/cpu/cpu.cfs_period_us") as f:
                period = int(f.read())
        except (OSError, ValueError):
            return None

    if quota <= 0 or period <= 0:
        return None
    return quota / period


def _default_workers():
    cpus = _cgroup_cpus()
    if cpus is None:
        cpus = multiprocessing.cpu_count()
    return max(2, min(int(cpus * 2 + 1), MAX_WORKERS))


workers = int(os.environ.get("GUNICORN_WORKERS") or _default_workers())

# ASGI worker: the app is served through deployment_gui.asgi:application so the
# MCP server (Streamable HTTP) can be mounted alongside Django in one process.
# Django 5 runs the existing sync views and sync middleware unchanged under ASGI.
#
# uvicorn_worker (the maintained `uvicorn-worker` package) rather than the
# in-tree uvicorn.workers, which still exists but warns on every worker boot:
# "The `uvicorn.workers` module is deprecated. Please use `uvicorn-worker`."
#
# Rollback lever: setting GUNICORN_WORKER_CLASS=sync and pointing the CMD back at
# deployment_gui.wsgi:application restores the previous serving path exactly.
# wsgi.py is deliberately retained for that purpose.
worker_class = os.environ.get("GUNICORN_WORKER_CLASS", "uvicorn_worker.UvicornWorker")
worker_connections = 1000
timeout = 120
keepalive = 5

# Logging
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "neuronsphere-deployment-gui"

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# Graceful timeout
graceful_timeout = 30

# Max requests before worker restart (helps with memory leaks)
max_requests = 1000
max_requests_jitter = 50
