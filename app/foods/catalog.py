import csv
import os

import structlog
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.utils import DataError, IntegrityError

from foods.models import DietLabel, FoodCatalog
from foods.normalize import normalize_food_name
from foods.openai_client import OpenAIClient

log = structlog.get_logger(__name__)

SEED_PATH = os.path.join(os.path.dirname(__file__), "seeds", "food_catalog.csv")

# Returns cleaned data or raise ValidationError
def _validate_catalog_row(row):
    errors = {}
    cleaned = {}

    raw = (row.get("food_name") or "").strip()
    if not raw:
        errors["food_name"] = "required"
    else:
        norm = normalize_food_name(raw)
        max_len = FoodCatalog._meta.get_field("food_name").max_length
        if len(norm) > max_len:
            errors["food_name"] = f"length {len(norm)} > max {max_len}"
        cleaned["food_name"] = norm

    diet = (row.get("diet") or "").strip().lower()
    valid = {DietLabel.VEGAN, DietLabel.VEGETARIAN, DietLabel.OMNIVORE, DietLabel.UNKNOWN}
    if diet not in valid:
        diet = DietLabel.UNKNOWN
    cleaned["diet"] = diet

    source = (row.get("source") or "static").strip().lower()
    max_src = FoodCatalog._meta.get_field("source").max_length
    if len(source) > max_src:
        errors["source"] = f"length {len(source)} > max {max_src}"
    cleaned["source"] = source

    if errors:
        raise ValidationError(errors)

    return cleaned

# Load the seed CSV
def ensure_seed_loaded():
    if not os.path.exists(SEED_PATH):
        log.warning("catalog.seed_missing", path=SEED_PATH)
        return 0

    inserts = 0
    with open(SEED_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        with transaction.atomic():
            for row_num, row in enumerate(reader, start=2):
                try:
                    data = _validate_catalog_row(row)
                    _, created = FoodCatalog.objects.update_or_create(
                        food_name=data["food_name"],
                        defaults={"diet": data["diet"], "source": data["source"], "confidence": None},
                    )
                    inserts += int(created)

                except ValidationError as ve:
                    # Column-level info
                    log.error(
                        "catalog.seed_row_invalid",
                        row_num=row_num,
                        errors=getattr(ve, "message_dict", {"__all__": ve.messages}),
                        row=row,
                    )
                    # Re-raise to trigger rollback
                    raise

                except (DataError, IntegrityError) as dbx:
                    # DB-layer issues
                    log.error(
                        "catalog.seed_row_db_error",
                        row_num=row_num,
                        error=str(dbx),
                        row=row,
                    )
                    raise

    if inserts:
        log.info("catalog.seed_loaded", count=inserts)
    return inserts

def lookup(food_name):
    norm = normalize_food_name(food_name)
    try:
        obj = FoodCatalog.objects.get(food_name=norm)
        log.info("classify.catalog_hit", food=norm, label=obj.diet)
        return obj
    except FoodCatalog.DoesNotExist:
        log.info("classify.catalog_miss", food=norm)
        return None

# If not in catalog, ask LLM
def expand_with_llm(food_name, client=None):
    norm = normalize_food_name(food_name)
    if client is None:
        client = OpenAIClient()

    result = client.classify_food_diet(norm)

    if isinstance(result, tuple):
        raw_label, confidence = result
    else:
        raw_label, confidence = result, None

    # Normalize label
    label_norm = (raw_label or "").strip().lower()
    allowed = {DietLabel.VEGAN, DietLabel.VEGETARIAN, DietLabel.OMNIVORE}

    if label_norm not in allowed:
        log.warning("catalog.llm_unmapped_label", food=norm, got=raw_label)
        return None

    obj, created = FoodCatalog.objects.update_or_create(
        food_name=norm,
        defaults={
            "diet": label_norm,
            "source": "llm",
            "confidence": confidence
        },
    )

    log.info(
        "catalog.llm_cached",
        food=norm,
        diet=label_norm,
        confidence=confidence,
        created=created,
        cost_usd=round(client.cost_usd(), 6)
    )
    return obj
