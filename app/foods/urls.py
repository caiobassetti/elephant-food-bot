from django.urls import path
from .views import (
    dashboard,
    simulate,
    diets_png,
    veg_users_view,
    run_simulation,
)


api_urlpatterns = [
    path("veg-users/", veg_users_view, name="veg-users"),
]

ui_urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("simulate", simulate, name="simulate"),
    path("diets.png", diets_png, name="diets-png"),
]

ops_urlpatterns = [
    path("run-sim/", run_simulation, name="run-sim"),
]
