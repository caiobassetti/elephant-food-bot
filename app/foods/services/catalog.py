import csv
import os

import structlog
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.utils import DataError, IntegrityError

from foods.models import FoodCatalog, DietLabel
from foods.utils.normalize import normalize_food_name
from foods.utils.openai_client import OpenAIClient

log = structlog.get_logger(__name__)

SEED_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "seeds", "food_catalog.csv")

def _validate_catalog_row(row):
    """
    Returns cleaned data or raise ValidationError.
    """
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

def ensure_seed_loaded():
    """
    Load the seed CSV and returns number of inserts performed.
    """
    if not os.path.exists(SEED_PATH):
        log.warning("catalog.seed_missing", path=SEED_PATH)
        return 0

    inserts = 0
    with open(SEED_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # Ensures one DB transaction for the entire catalog,
        # either fully created or rolled back in case of error at any point
        with transaction.atomic():
            for row_num, row in enumerate(reader, start=2):
                try:
                    data = _validate_catalog_row(row)
                    _, created = FoodCatalog.objects.update_or_create(
                        food_name=data["food_name"],
                        defaults={"diet": data["diet"], "source": data["source"], "confidence": None},
                    )
                    inserts += int(created)

                except ValidationError as ve: # Column-level info
                    log.error(
                        "catalog.seed_row_invalid",
                        row_num=row_num,
                        errors=getattr(ve, "message_dict", {"__all__": ve.messages}),
                        row=row,
                    )
                    raise # Re-raise to trigger rollback of the whole file

                except (DataError, IntegrityError) as dbx: # DB-layer issues
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
        return FoodCatalog.objects.get(food_name=norm)
    except FoodCatalog.DoesNotExist:
        return None

def expand_with_llm(food_name, client = None):
    """
    If not in catalog, ask LLM, persist result in db
    """
    norm = normalize_food_name(food_name)
    if client is None:
        client = OpenAIClient()

    label = client.classify_food_diet(norm)
    if label not in {DietLabel.VEGAN, DietLabel.VEGETARIAN, DietLabel.OMNIVORE}:
        return None

    obj, _ = FoodCatalog.objects.update_or_create(
        food_name=norm,
        defaults={"diet": label, "source": "llm", "confidence": None}
    )
    log.info("catalog.llm_cached", food=norm, diet=label, cost_usd=round(client.usage.cost_usd, 6))
    return obj
