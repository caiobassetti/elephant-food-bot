from django.urls import path

from .views_ops import run_simulation

urlpatterns = [
    path("ops/run-sim/", run_simulation, name="ops-run-sim"),
]
