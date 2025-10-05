from django.contrib import admin
from django.urls import include, path

from foods.urls import api_urlpatterns, ui_urlpatterns, ops_urlpatterns

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include((api_urlpatterns, "foods"), namespace="api")),
    path("ui/", include((ui_urlpatterns, "foods"), namespace="ui")),
    path("ops/", include((ops_urlpatterns, "foods"), namespace="ops")),
]
