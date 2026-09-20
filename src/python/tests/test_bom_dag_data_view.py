"""Unit tests for bom_dag_data's response caching and backend call count.

Extracts just the view function's source (skipping its decorators, which live
above the `def` line the extraction regex anchors on) from views.py, mirroring
the approach in test_bom_dag_elements.py. `get_api_client_for_request` is
stubbed since the view only ever passes `request` through to it.
"""
import os
import re
import sys
import textwrap
import unittest

try:
    import django
    from django.conf import settings

    if not settings.configured:
        settings.configure(
            DEBUG=False,
            DEPLOYMENT_BOM_CACHE_TTL=1234,
            CACHES={
                "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
            },
            INSTALLED_APPS=[],
        )
        django.setup()

    _DJANGO_AVAILABLE = True
except ImportError:
    _DJANGO_AVAILABLE = False


@unittest.skipUnless(_DJANGO_AVAILABLE, "Django not available in this environment")
class TestBomDagDataCaching(unittest.TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.cache = cache

        _VIEWS_PATH = os.path.join(
            os.path.dirname(__file__), "..", "deployments", "views.py"
        )

        def _extract_function_source(name):
            with open(_VIEWS_PATH, "r", encoding="utf-8") as fh:
                text = fh.read()
            match = re.search(
                rf"^def {name}\([\s\S]+?(?=\n(?:@|def )|\Z)",
                text,
                re.MULTILINE,
            )
            if not match:
                raise RuntimeError(f"{name} not found in views.py")
            return textwrap.dedent(match.group(0))

        from django.core.cache import cache as django_cache
        from django.http import JsonResponse

        self.get_calls = []

        class _Resp:
            def __init__(self, success, data=None, error=None):
                self.success = success
                self.data = data
                self.error = error

        class _Client:
            def __init__(self, bom_data=None):
                self.bom_calls = 0
                self._bom_data = bom_data if bom_data is not None else []

            def get_deployment_bom(self, environment_type):
                self.bom_calls += 1
                return _Resp(True, data=self._bom_data)

        self.client = _Client()

        def _fake_get_api_client_for_request(request):
            return self.client

        self._module_globals = {
            "cache": django_cache,
            "settings": settings,
            "JsonResponse": JsonResponse,
            "get_api_client_for_request": _fake_get_api_client_for_request,
        }
        from deployments.services.bom_query import build_bom_dag_elements

        self._module_globals["_build_bom_dag_elements"] = build_bom_dag_elements
        exec(_extract_function_source("bom_dag_data"), self._module_globals)
        self.bom_dag_data = self._module_globals["bom_dag_data"]

    def test_first_call_populates_cache_and_calls_client(self):
        response = self.bom_dag_data(None, "dev")

        self.assertEqual(self.client.bom_calls, 1)
        self.assertIsNotNone(self.cache.get("bom_dag:dev"))
        self.assertEqual(response.status_code, 200)

    def test_second_call_hits_cache_without_calling_client_again(self):
        self.bom_dag_data(None, "dev")
        self.bom_dag_data(None, "dev")

        self.assertEqual(self.client.bom_calls, 1)

    def test_many_unique_class_version_pairs_still_one_backend_call(self):
        """Regression test for the N+1 fix: a BOM with many unique (repo_class,
        version) pairs must not trigger per-pair classification round trips —
        the view should make exactly one get_deployment_bom call no matter how
        many distinct pairs are present."""
        bom_data = [
            {
                "repo_instance_name": f"svc-{i}",
                "repo_class_name": f"hmd-ms-svc-{i}",
                "repo_class_version": "1.0.0",
                "status": "DEPLOYED",
                "dependencies": {},
            }
            for i in range(25)
        ]
        self.client._bom_data = bom_data

        response = self.bom_dag_data(None, "dev")

        self.assertEqual(self.client.bom_calls, 1)
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
