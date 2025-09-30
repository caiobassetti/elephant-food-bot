import uuid

import structlog
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from foods.models import UserProfile, Conversation, FavoriteFood, FoodCatalog, DietLabel, MessageRole
from foods.services import catalog
from foods.services.diet import derive_user_diet
from foods.utils.normalize import normalize_food_name
from foods.utils.openai_client import OpenAIClient, OPENAI_MODEL

log = structlog.get_logger(__name__)

A_QUESTION = "What are your top 3 favorite foods?"

SLIDING = 2


def _load_foods_sorted():
    """
    Load all catalog foods in a stable order.
    """
    foods = list(
        FoodCatalog.objects.order_by("food_name").values_list("food_name", flat=True)
    )
    if len(foods) < 3:
        raise CommandError("Catalog has fewer than 3 foods. Did the seed load?")
    return foods


def _pick_three_for_index(all_foods, idx, stride=SLIDING):
    """
    Takes 3 consecutive items from the sorted catalog.
    """
    n = len(all_foods)
    start = (idx * stride) % n
    return [
        all_foods[start],
        all_foods[(start + 1) % n],
        all_foods[(start + 2) % n],
    ]


class Command(BaseCommand):
    help = "Simulate favorite-food conversations, persist users, conversations, favorites, and derived diets."

    def add_arguments(self, parser):
        parser.add_argument("--runs", type=int, default=100, help="Number of users to simulate")
        parser.add_argument("--run-id", type=str, default="", help="Optional run id (uuid)")

    def handle(self, *args, **opts):
        runs = int(opts.get("runs", 100))
        run_id = opts.get("run_id") or str(uuid.uuid4())

        try:
            run_uuid = uuid.UUID(run_id)
        except Exception:
            run_uuid = uuid.uuid4()

        # Ensure catalog
        catalog.ensure_seed_loaded()
        all_foods = _load_foods_sorted()

        # Client used only if a catalog miss occurs
        client = OpenAIClient()
        model_label = "dry-run" if client.dry_run else OPENAI_MODEL

        self.stdout.write(self.style.MIGRATE_HEADING(f"simulate_foods: runs={runs} run_id={run_id}"))

        for i in range(runs):
            with transaction.atomic():
                # Create user with UNKNOWN diet initially
                user = UserProfile.objects.create(diet=DietLabel.UNKNOWN, run_id=run_uuid)

                # Store A's question
                conv_a = Conversation.objects.create(
                    user=user,
                    role=MessageRole.A,
                    prompt=A_QUESTION,
                    response="",
                    model="",
                    prompt_tokens=None,
                    completion_tokens=None,
                    total_tokens=None,
                    estimated_cost_usd=None,
                    run_id=run_uuid,
                )

                # Top-3 foods
                foods = _pick_three_for_index(all_foods, i)

                # Store B's response
                b_response = ", ".join(foods)
                Conversation.objects.create(
                    user=user,
                    role=MessageRole.B,
                    prompt="seed",
                    response=b_response,
                    model=model_label,
                    prompt_tokens=getattr(client, "input_tokens", 0) or 0,
                    completion_tokens=getattr(client, "output_tokens", 0) or 0,
                    total_tokens=(getattr(client, "input_tokens", 0) or 0) + (getattr(client, "output_tokens", 0) or 0),
                    estimated_cost_usd=(client.cost_usd() if hasattr(client, "cost_usd") else 0.0),
                    run_id=run_uuid,
                )

                # Insert favorites with normalization + catalog lookup/expansion
                diets_seen = []
                for rank, raw in enumerate(foods, start=1):
                    norm = normalize_food_name(raw)
                    cat = catalog.lookup(norm)
                    if cat is None:
                        # Only triggers if a food not in catalog
                        cat = catalog.expand_with_llm(norm, client=client)

                    FavoriteFood.objects.create(
                        user=user,
                        rank=rank,
                        name_raw=raw,
                        food_name=norm,
                        catalog=cat,
                    )
                    diets_seen.append(cat.diet if cat else DietLabel.UNKNOWN)

                # Derive user's diet from the three food diets
                user.diet = derive_user_diet(diets_seen)
                user.save(update_fields=["diet"])

                log.info(
                    "simulation.user_done",
                    user_id=str(user.id),
                    run_id=str(run_uuid),
                    foods=foods,
                    derived_diet=user.diet,
                )

        # Summarize token usage/cost
        usage_holder = getattr(client, "usage", client)
        input_tokens = int(getattr(usage_holder, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage_holder, "output_tokens", 0) or 0)
        cost_attr = getattr(usage_holder, "cost_usd", 0.0)
        cost_usd = cost_attr() if callable(cost_attr) else float(cost_attr or 0.0)

        self.stdout.write(self.style.SUCCESS(
            f"Done. users={runs} run_id={run_id} "
            f"llm_input_tokens={input_tokens} "
            f"llm_output_tokens={output_tokens} "
            f"llm_cost_usd≈{cost_usd:.5f}"
        ))
