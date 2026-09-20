"""Unit tests for ``OktaTokenExpiryMiddleware``.

Django settings are stubbed via ``settings.configure(...)`` before importing the
middleware (matches ``test_api_client``). The ``SocialToken``/``SocialAccount``
lookups and ``logout`` are patched, so these tests need no database or allauth
app — they exercise only the middleware's branching.
"""
import os
import sys
import unittest
from datetime import timedelta
from unittest import mock

try:
    import django
    from django.conf import settings

    if not settings.configured:
        settings.configure(
            DEBUG=False,
            ALLOWED_HOSTS=["testserver"],
            STATIC_URL="/static/",
            LOGIN_URL="account_login",
            CACHES={
                "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
            },
            INSTALLED_APPS=[],
        )
        django.setup()

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    from django.test import RequestFactory, override_settings  # noqa: E402
    from django.utils import timezone  # noqa: E402

    from deployments import middleware as mw  # noqa: E402

    _DJANGO_AVAILABLE = True
except ImportError:
    _DJANGO_AVAILABLE = False


@unittest.skipUnless(_DJANGO_AVAILABLE, "Django not installed in this environment")
class OktaTokenExpiryMiddlewareTests(unittest.TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.sentinel = object()  # what get_response returns on pass-through
        self.get_response = mock.Mock(return_value=self.sentinel)
        self.middleware = mw.OktaTokenExpiryMiddleware(self.get_response)

    def _request(self, path="/environments/dev/", htmx=False):
        request = self.factory.get(path)
        request.user = mock.Mock(is_authenticated=True, username="alice")
        request.htmx = htmx
        return request

    def _token(self, expires_at, token="tok"):
        return mock.Mock(token=token, expires_at=expires_at)

    # --- expired token -----------------------------------------------------

    def test_expired_token_redirects_to_login_with_next(self):
        request = self._request("/environments/dev/")
        with mock.patch.object(
            mw,
            "get_okta_social_token",
            return_value=self._token(timezone.now() - timedelta(minutes=1)),
        ), mock.patch.object(
            mw, "reverse", return_value="/accounts/login/"
        ), mock.patch.object(
            mw, "logout"
        ) as logout:
            response = self.middleware(request)

        logout.assert_called_once_with(request)
        self.get_response.assert_not_called()
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)
        self.assertIn("next=%2Fenvironments%2Fdev%2F", response.url)

    def test_expired_token_on_htmx_returns_hx_redirect(self):
        request = self._request("/bom-table/", htmx=True)
        with mock.patch.object(
            mw,
            "get_okta_social_token",
            return_value=self._token(timezone.now() - timedelta(seconds=5)),
        ), mock.patch.object(
            mw, "reverse", return_value="/accounts/login/"
        ), mock.patch.object(
            mw, "logout"
        ):
            response = self.middleware(request)

        # HttpResponseClientRedirect is a 200 carrying HX-Redirect, so htmx does
        # a full-page navigation instead of swapping the login page into a panel.
        self.assertEqual(response.status_code, 200)
        self.assertIn("/accounts/login/", response["HX-Redirect"])

    def test_token_within_buffer_is_treated_as_expired(self):
        # Expires 10s out, inside the 30s buffer -> reauth.
        request = self._request()
        with mock.patch.object(
            mw,
            "get_okta_social_token",
            return_value=self._token(timezone.now() + timedelta(seconds=10)),
        ), mock.patch.object(
            mw, "reverse", return_value="/accounts/login/"
        ), mock.patch.object(
            mw, "logout"
        ):
            response = self.middleware(request)

        self.assertEqual(response.status_code, 302)
        self.get_response.assert_not_called()

    # --- valid token -------------------------------------------------------

    def test_valid_token_passes_through(self):
        request = self._request()
        with mock.patch.object(
            mw,
            "get_okta_social_token",
            return_value=self._token(timezone.now() + timedelta(hours=1)),
        ), mock.patch.object(mw, "logout") as logout:
            response = self.middleware(request)

        self.assertIs(response, self.sentinel)
        self.get_response.assert_called_once_with(request)
        logout.assert_not_called()

    def test_null_expiry_fails_open(self):
        request = self._request()
        with mock.patch.object(
            mw,
            "get_okta_social_token",
            return_value=self._token(None),
        ), mock.patch.object(mw, "logout"):
            response = self.middleware(request)

        self.assertIs(response, self.sentinel)

    # --- non-Okta / unauthenticated / exempt -------------------------------

    def test_local_user_without_okta_account_passes_through(self):
        request = self._request()
        with mock.patch.object(
            mw, "get_okta_social_token", return_value=None
        ), mock.patch.object(mw, "get_okta_social_account", return_value=None):
            response = self.middleware(request)

        self.assertIs(response, self.sentinel)

    def test_okta_user_missing_token_row_reauths(self):
        request = self._request()
        with mock.patch.object(
            mw, "get_okta_social_token", return_value=None
        ), mock.patch.object(
            mw, "get_okta_social_account", return_value=object()
        ), mock.patch.object(
            mw, "reverse", return_value="/accounts/login/"
        ), mock.patch.object(
            mw, "logout"
        ):
            response = self.middleware(request)

        self.assertEqual(response.status_code, 302)

    def test_unauthenticated_request_passes_through(self):
        request = self.factory.get("/environments/dev/")
        request.user = mock.Mock(is_authenticated=False)
        request.htmx = False
        response = self.middleware(request)
        self.assertIs(response, self.sentinel)

    def test_exempt_paths_never_redirect(self):
        # Pin STATIC_URL so /static/ is recognized regardless of which test
        # module won the shared settings.configure() race.
        with override_settings(STATIC_URL="/static/"):
            for path in ("/accounts/login/", "/health/", "/static/app.css"):
                request = self._request(path)
                with mock.patch.object(
                    mw,
                    "get_okta_social_token",
                    return_value=self._token(timezone.now() - timedelta(hours=1)),
                ) as get_token:
                    response = self.middleware(request)
                self.assertIs(response, self.sentinel, f"{path} should be exempt")
                get_token.assert_not_called()


if __name__ == "__main__":
    unittest.main()
