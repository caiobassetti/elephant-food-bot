import uuid

import structlog
from django.core.management.base import BaseCommand
from django.db import transaction
from foods import catalog
from foods.diet import derive_user_diet
from foods.models import (
    Conversation,
    DietLabel,
    FavoriteFood,
    MessageRole,
    UserProfile,
)
from foods.normalize import normalize_food_name
from foods.openai_client import (
    OPENAI_MODEL,
    PRICE_PER_1K_INPUT,
    PRICE_PER_1K_OUTPUT,
    OpenAIClient,
)

log = structlog.get_logger(__name__)


class Command(BaseCommand):
    help = "Simulate favorite-food conversations, persist users, conversations, favorites, and derived diets."

    def add_arguments(self, parser):
        parser.add_argument("--runs", type=int, default=100, help="Number of users to simulate")

    def handle(self, *args, **opts):
        runs = int(opts.get("runs", 100))
        run_uuid = uuid.uuid4()

        # Ensure catalog seeded/available
        catalog.ensure_seed_loaded()

        client = OpenAIClient()
        model_label = OPENAI_MODEL

        self.stdout.write(self.style.MIGRATE_HEADING(f"simulate_foods: runs={runs} run_id={run_uuid}"))

        for i in range(runs):
            with transaction.atomic():
                # Create user with UNKNOWN diet initially
                user = UserProfile.objects.create(diet=DietLabel.UNKNOWN, run_id=run_uuid)

                # Compose prompt (base + seed)
                seed_text = f"seed:{i}"
                prompt = '''What is your top-3 favorite foods?
                Return exactly three different general foods (not brand names),
                separated by a comma and a space.
                Output only the three food names, no numbers, no explanations,
                no quotes, and no extra text.'''
                composed_prompt = prompt + seed_text

                # Track client token counters before top-3 call
                a_in_before = int(getattr(client, "input_tokens", 0) or 0)
                a_out_before = int(getattr(client, "output_tokens", 0) or 0)

                # OpenAI call to ask for three foods
                foods = client.ask_top_three_favorite_foods(composed_prompt)

                # Client token counters after top-3 call
                a_in_after = int(getattr(client, "input_tokens", 0) or 0)
                a_out_after = int(getattr(client, "output_tokens", 0) or 0)
                a_prompt_tokens = max(0, a_in_after - a_in_before)
                a_completion_tokens = max(0, a_out_after - a_out_before)
                a_total_tokens = a_prompt_tokens + a_completion_tokens
                a_cost_usd = (a_prompt_tokens / 1000.0) * PRICE_PER_1K_INPUT + \
                             (a_completion_tokens / 1000.0) * PRICE_PER_1K_OUTPUT

                # Store Conversation A
                Conversation.objects.create(
                    user=user,
                    role=MessageRole.A,
                    prompt=composed_prompt,
                    response="",
                    model=model_label,
                    prompt_tokens=a_prompt_tokens,
                    completion_tokens=a_completion_tokens,
                    total_tokens=a_total_tokens,
                    estimated_cost_usd=round(a_cost_usd, 6),
                    run_id=run_uuid,
                )

                # Store Conversation B
                b_response_text = ", ".join(foods)
                b_msg = Conversation.objects.create(
                    user=user,
                    role=MessageRole.B,
                    prompt=composed_prompt,
                    response=b_response_text,
                    model=model_label,
                    prompt_tokens=None,
                    completion_tokens=None,
                    total_tokens=None,
                    estimated_cost_usd=None,
                    run_id=run_uuid,
                )

                # Track client counters before classification loop
                b_in_before = int(getattr(client, "input_tokens", 0) or 0)
                b_out_before = int(getattr(client, "output_tokens", 0) or 0)

                # Insert favorites with normalization + catalog lookup/expansion
                diets_seen = []
                for rank, raw in enumerate(foods, start=1):
                    norm = normalize_food_name(raw)
                    cat = catalog.lookup(norm)
                    if cat is None:
                        # LLM classification, only triggers if a food not in catalog
                        cat = catalog.expand_with_llm(norm, client=client)

                    FavoriteFood.objects.create(
                        user=user,
                        rank=rank,
                        name_raw=raw,
                        food_name=norm,
                        catalog=cat,
                    )
                    diets_seen.append(cat.diet if cat else DietLabel.UNKNOWN)

                # Derive user's diet from the three labels
                user.diet = derive_user_diet(diets_seen)
                user.save(update_fields=["diet"])

                # Client counters after classification loop
                b_in_after = int(getattr(client, "input_tokens", 0) or 0)
                b_out_after = int(getattr(client, "output_tokens", 0) or 0)
                b_prompt_tokens = max(0, b_in_after - b_in_before)
                b_completion_tokens = max(0, b_out_after - b_out_before)
                b_total_tokens = b_prompt_tokens + b_completion_tokens
                b_cost_usd = (b_prompt_tokens / 1000.0) * PRICE_PER_1K_INPUT + \
                             (b_completion_tokens / 1000.0) * PRICE_PER_1K_OUTPUT

                # Update Conversation B with token/cost
                b_msg.prompt_tokens = b_prompt_tokens
                b_msg.completion_tokens = b_completion_tokens
                b_msg.total_tokens = b_total_tokens
                b_msg.estimated_cost_usd = round(b_cost_usd, 6)
                b_msg.save(update_fields=[
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "estimated_cost_usd"
                ])

                log.info(
                    "simulation.user_done",
                    user_id=str(user.id),
                    run_id=str(run_uuid),
                    foods=foods,
                    derived_diet=user.diet,
                    a_tokens=a_total_tokens,
                    b_tokens=b_total_tokens,
                )

        # Summarize token/cost for the whole run
        input_tokens = int(getattr(client, "input_tokens", 0) or 0)
        output_tokens = int(getattr(client, "output_tokens", 0) or 0)
        total_cost = client.cost_usd()
        self.stdout.write(self.style.SUCCESS(
            f"Done. users={runs} run_id={run_uuid} "
            f"llm_input_tokens={input_tokens} "
            f"llm_output_tokens={output_tokens} "
            f"llm_cost_usd≈{total_cost:.5f}"
        ))
