from django.urls import path
from .views import VegUsersView

urlpatterns = [
    path("veg-users/", VegUsersView.as_view(), name="veg-users"),
]
