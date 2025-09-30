import pytest
from django.apps import apps

pytestmark = pytest.mark.django_db

def test_related_names_exist_and_work():
    # Verifies the reverse related_names (messages, foods)
    # exist and actually point to the created rows
    UserProfile = apps.get_model("foods", "UserProfile")
    Conversation = apps.get_model("foods", "Conversation")
    FavoriteFood = apps.get_model("foods", "FavoriteFood")

    from conftest import build_instance

    user = build_instance(UserProfile)
    # Conversation.user -> related_name="messages"
    conv = build_instance(Conversation, user=user)
    # FavoriteFood.user -> related_name="foods"
    food = build_instance(FavoriteFood, user=user)

    # Assert the reverse relation exists
    assert hasattr(user, "messages")
    assert hasattr(user, "foods")

    # Assert it includes the created instances
    assert conv in user.messages.all()
    assert food in user.foods.all()
