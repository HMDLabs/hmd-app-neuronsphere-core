"""URL configuration for NeuronSphere Deployment GUI."""
from importlib import util as importlib_util

from django.conf import settings
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("", include("deployments.urls")),
]

# Extra apps (settings.EXTRA_APPS) mount their routes at the root too, after
# the core's, so a premium overlay serves the paths it always did.
for _app in settings.EXTRA_APPS:
    if importlib_util.find_spec(f"{_app}.urls") is not None:
        urlpatterns.append(path("", include(f"{_app}.urls")))
