from django.urls import path

from . import views

app_name = "ns_service_views"

urlpatterns = [
    path("", views.index, name="index"),
    path("<str:environment>/", views.service_list, name="service_list"),
    path(
        "<str:environment>/<str:instance>/",
        views.service_detail,
        name="service_detail",
    ),
    path(
        "<str:environment>/<str:instance>/views/<path:rest>",
        views.proxy_view,
        name="proxy",
    ),
]
