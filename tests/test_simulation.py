import uuid

import pytest
from django.apps import apps
from django.core.management import call_command

from foods.models import (
    DietLabel,
    FoodCatalog,
    Conversation,
    UserProfile,
    FavoriteFood,
)

pytestmark = pytest.mark.django_db  # Allows DB access

# Ensure at least three rows exist so simulate_foods check passes
def _seed_catalog_minimum():
    FoodCatalog.objects.update_or_create(
        food_name="banana", defaults={"diet": DietLabel.VEGAN, "source": "static"}
    )
    FoodCatalog.objects.update_or_create(
        food_name="avocado toast", defaults={"diet": DietLabel.VEGAN, "source": "static"}
    )
    FoodCatalog.objects.update_or_create(
        food_name="hummus", defaults={"diet": DietLabel.VEGAN, "source": "static"}
    )

# Smoke test: command runs, creates conversations, and does not hit real OpenAI
def test_simulate_foods_command_smoke_runs_with_fake_client(monkeypatch):
    _seed_catalog_minimum()

    class _FakeOpenAI:
        def __init__(self):
            self.input_tokens = 0
            self.output_tokens = 0

        def cost_usd(self):
            return 0.0

        def ask_top_three_favorite_foods(self, prompt):
            # Return three known foods so classification is not triggered
            self.input_tokens += 10
            self.output_tokens += 3
            return ["banana", "avocado toast", "hummus"]

        def classify_food_diet(self, food_name):
            raise AssertionError("classify_food_diet should not be called in smoke test")

    import foods.management.commands.simulate_foods as sim
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(sim, "OpenAIClient", _FakeOpenAI, raising=True)

    call_command("simulate_foods", runs=2)

    assert UserProfile.objects.count() == 2
    # Two messages per user (A and B)
    assert Conversation.objects.count() == 4
    # 3 favorites per user
    assert FavoriteFood.objects.count() == 6


# All 3 foods already in catalog -> no classification
# Conversation A gets tokens (top-3 call), Conversation B stays at zero
def test_catalog_first_records_tokens_in_A_but_not_B(monkeypatch):
    _seed_catalog_minimum()

    class _FakeOpenAI:
        def __init__(self):
            self.input_tokens = 0
            self.output_tokens = 0

        def cost_usd(self):
            return 0.0

        def ask_top_three_favorite_foods(self, prompt):
            self.input_tokens += 50
            self.output_tokens += 10
            return ["banana", "avocado toast", "hummus"]

        def classify_food_diet(self, food_name):
            raise AssertionError("classify_food_diet should not be called when all foods are in catalog")

    import foods.management.commands.simulate_foods as sim
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(sim, "OpenAIClient", _FakeOpenAI, raising=True)

    call_command("simulate_foods", runs=1)

    a = Conversation.objects.get(role="A")
    b = Conversation.objects.get(role="B")

    # A holds only the top-3
    assert a.prompt_tokens == 50
    assert a.completion_tokens == 10
    assert a.total_tokens == 60
    # B must be zero (no classification happened)
    assert (b.prompt_tokens or 0) == 0
    assert (b.completion_tokens or 0) == 0
    assert (b.total_tokens or 0) == 0


# If at least one food is unknown, classification fires and B records those token
def test_unknown_food_triggers_classification_tokens_in_B(monkeypatch):
    _seed_catalog_minimum()

    class _FakeOpenAI:
        def __init__(self):
            self.input_tokens = 0
            self.output_tokens = 0

        def cost_usd(self):
            return 0.0

        def ask_top_three_favorite_foods(self, prompt):
            # Top-3 call usage
            self.input_tokens += 30
            self.output_tokens += 8
            return ["banana", "mystery stew", "avocado toast"]

        def classify_food_diet(self, food_name):
            # Classification usage for the unknown one
            assert food_name == "mystery stew"
            self.input_tokens += 20
            self.output_tokens += 6
            return "omnivore"

    import foods.management.commands.simulate_foods as sim
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(sim, "OpenAIClient", _FakeOpenAI, raising=True)

    call_command("simulate_foods", runs=1)

    a = Conversation.objects.get(role="A")
    b = Conversation.objects.get(role="B")

    # A captured only top-3
    assert a.prompt_tokens == 30
    assert a.completion_tokens == 8
    assert a.total_tokens == 38

    # B captured only classification
    assert b.prompt_tokens == 20
    assert b.completion_tokens == 6
    assert b.total_tokens == 26

    # Catalog updated by LLM
    cat = FoodCatalog.objects.get(food_name="mystery stew")
    assert cat.source == "llm"
    assert cat.diet == DietLabel.OMNIVORE

    # User has 3 favorites and derived diet is omnivore
    user = UserProfile.objects.first()
    assert user is not None
    assert user.foods.count() == 3
    assert user.diet == DietLabel.OMNIVORE


# Budget 1: top-3 succeeds, classification exceeds budget and raises
# Transaction should roll back the user's creations for that run
def test_budget_limiter_stops_run_and_rolls_back(monkeypatch):
    _seed_catalog_minimum()

    # Simulate a per-client budget used by the fake
    class _BudgetedFake:
        def __init__(self):
            # allow only one call total
            self.input_tokens = 0
            self.output_tokens = 0
            self._budget = 1

        def _consume(self, reason):
            if self._budget <= 0:
                raise RuntimeError(f"LLM call budget exceeded while attempting: {reason}")
            self._budget -= 1

        def cost_usd(self):
            return 0.0

        def ask_top_three_favorite_foods(self, prompt):
            self._consume("ask_top_three_favorite_foods")
            self.input_tokens += 10
            self.output_tokens += 3
            return ["banana", "unknown dish", "avocado toast"]

        def classify_food_diet(self, food_name):
            self._consume("classify_food_diet")
            self.input_tokens += 10
            self.output_tokens += 3
            return "vegan"

    import foods.management.commands.simulate_foods as sim
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(sim, "OpenAIClient", _BudgetedFake, raising=True)

    with pytest.raises(RuntimeError, match="LLM call budget exceeded"):
        call_command("simulate_foods", runs=1)

    assert UserProfile.objects.count() == 0
    assert Conversation.objects.count() == 0
    assert FavoriteFood.objects.count() == 0
