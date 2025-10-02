from django.urls import path
from . import views_ui

urlpatterns = [
    path("", views_ui.dashboard, name="dashboard"),
    path("simulate", views_ui.simulate, name="simulate"),
    path("diets.png", views_ui.diets_png, name="diets-png"),
]
