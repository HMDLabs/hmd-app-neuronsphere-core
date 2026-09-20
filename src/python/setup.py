"""Setup configuration for NeuronSphere Deployment GUI."""
from pathlib import Path
from setuptools import setup, find_packages

repo_dir = Path(__file__).absolute().parent.parent.parent
version_file = repo_dir / "meta-data" / "VERSION"

with open(version_file, "r") as vfl:
    version = vfl.read().strip()

setup(
    name="hmd-app-neuronsphere-core",
    version=version,
    description="Django/HTMX GUI for NeuronSphere Deployment Service",
    author="HMD Labs",
    author_email="dev@hmdlabs.io",
    license="Apache 2.0",
    packages=find_packages(),
    include_package_data=True,
    python_requires=">=3.11",
    install_requires=[
        "Django>=5.0,<5.1",
        "gunicorn>=21.2.0",
        "whitenoise>=6.6.0",
        "psycopg2-binary>=2.9.9",
        "django-allauth>=0.61.0",
        "django-htmx>=1.17.0",
        "httpx>=0.27.0",
        "python-json-logger>=2.0.7",
        "requests>=2.31.0",
        "PyJWT>=2.8.0",
        "cryptography>=41.0.0",
        "django-redis>=5.4.0",
        # MCP server (see ns_mcp/) and the ASGI worker that serves it
        "fastmcp>=3.4,<4",
        "uvicorn[standard]>=0.30",
        "uvicorn-worker>=0.3",
    ],
)
