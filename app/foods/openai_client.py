import json
import os
import re
import time

import structlog

from .normalize import normalize_food_name
from django.db.models import F

log = structlog.get_logger(__name__)

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Price in USD per 1K tokens
PRICE_PER_1K_INPUT = float(os.getenv("OPENAI_PRICE_PER_1K_INPUT", "0.150"))
PRICE_PER_1K_OUTPUT = float(os.getenv("OPENAI_PRICE_PER_1K_OUTPUT", "0.600"))

# LLM calls limit (for tests/CI)
_CALL_BUDGET_ENV = os.getenv("EFB_LLM_CALL_BUDGET", "").strip()
CALL_BUDGET = None if _CALL_BUDGET_ENV == "" else max(0, int(_CALL_BUDGET_ENV))


class OpenAIClient:
    def __init__(self):
        self._dry_run = os.environ.get("EFB_DRY_RUN") == "1"

        if self._dry_run == 0:
            if not OPENAI_API_KEY:
                raise RuntimeError("OPENAI_API_KEY is required for live runs.")
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=OPENAI_API_KEY)
            except Exception as e:
                log.warning("openai_import_failed", error=str(e))
                raise

        self.input_tokens = 0
        self.output_tokens = 0

    # Budget control
    def _consume_budget(self, reason):
        global CALL_BUDGET
        if CALL_BUDGET is None:
            return
        if CALL_BUDGET <= 0:
            raise RuntimeError(f"LLM call budget exceeded while attempting: {reason}")
        CALL_BUDGET -= 1

    # Token/cost accounting
    def cost_usd(self):
        return (self.input_tokens / 1000.0) * PRICE_PER_1K_INPUT + \
               (self.output_tokens / 1000.0) * PRICE_PER_1K_OUTPUT

    @staticmethod
    def _strip_markdown_fences(s):
        s = s.strip()
        s = re.sub(r"^\s*```(?:json|JSON)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```\s*$", "", s)
        return s.strip()

    @staticmethod
    def _extract_first_json_array(s):
        m = re.search(r"\[\s*.*?\s*\]", s, flags=re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
            return data
        except Exception:
            return None

    @staticmethod
    def _parse_three_foods(text):
        s = (text or "").strip()
        # Strip markdown fences
        s1 = OpenAIClient._strip_markdown_fences(s)
        # Try JSON parse
        try:
            data = json.loads(s1)
            if isinstance(data, list):
                items = [str(x).strip() for x in data if str(x).strip()]
                if len(items) == 3:
                    return items
        except Exception:
            pass

        # Try extracting JSON array anywhere in text
        data = OpenAIClient._extract_first_json_array(s1)
        if isinstance(data, list) and len(data) == 3:
            items = [str(x).strip() for x in data if str(x).strip()]
            if len(items) == 3:
                return items

        # Try to recover quoted strings
        quoted = re.findall(r'"([^"]+)"', s1)
        quoted = [q.strip() for q in quoted if q.strip()]
        if len(quoted) == 3:
            return quoted

        # Try to split on commas/newlines/semicolons/brackets
        parts = [p.strip() for p in re.split(r"[,\n;]", s1) if p.strip()]

        # Remove common wrappers from each part
        cleaned = [re.sub(r"^[\[\]`*\-•\s]+|[\[\]`*\-•\s]+$", "", p) for p in parts]
        cleaned = [c for c in cleaned if c]
        if len(cleaned) == 3:
            return cleaned
        raise ValueError(f"Expected exactly 3 foods; got: {s[:120]}")

    # Send prompt and expect 3 foods back
    def ask_top_three_favorite_foods(self, composed_prompt):
        if self._dry_run:
            from .models import FoodCatalog
            foods = (
                FoodCatalog.objects
                .order_by("?")
                .values_list("food_name", flat=True)[:3]
            )
            foods = [f for f in foods if f]
            log.info("openai.call", got=len(foods), result="dry_run", ms=0)
            return foods

        self._consume_budget("ask_top_three_favorite_foods")

        system = (
            "Return exactly three food names as a JSON array of three short strings. "
            "No explanations, no markdown fences."
        )
        try:
            start = time.time()
            resp = self._client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": composed_prompt},
                ],
                temperature=0.9,
                # Nudge away from defaults
                presence_penalty=0.3,
                # Discouragement of repetition
                frequency_penalty=0.1,
            )
            ms = int((time.time() - start) * 1000)
            text = (resp.choices[0].message.content or "").strip()

            usage = getattr(resp, "usage", None)
            if usage:
                self.input_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
                self.output_tokens += int(getattr(usage, "completion_tokens", 0) or 0)

            foods = self._parse_three_foods(text)
            log.info("llm.top3", result=foods, ms=ms)
            return foods
        except Exception as e:
            # Include a snippet of the model text for debugging
            snippet = (text or "")[:160]
            log.warning("llm.error.top3", error=str(e), raw_snippet=snippet)
            raise

    def classify_food_diet(self, food_name):
        if self._dry_run:
            from .models import FoodCatalog
            norm = normalize_food_name(food_name)
            cat = (
                FoodCatalog.objects
                .filter(food_name=norm)
                .values("diet", "source", "confidence")
                .first()
            )
            if cat:
                log.info(
                    "llm.classify",
                    food=norm,
                    result=cat["diet"],
                    confidence=cat["confidence"],
                    ms=0,
                    got="catalog",
                )
                return cat["diet"], cat["confidence"]
            log.info("llm.classify", food=food_name, result="unknown", confidence=None, ms=0, got="dry_run-miss")
            return "unknown", None

        self._consume_budget("classify_food_diet")

        prompt = (
            "Classify the single food item below into one label:\n"
            "- VEGAN: contains no animal products.\n"
            "- VEGETARIAN: may include dairy/eggs, but no meat/fish.\n"
            "- OMNIVORE: includes meat or fish.\n"
            "Return STRICT JSON with two keys:\n"
            "{'diet': '<vegan|vegetarian|omnivore>', 'confidence': <float between 0 and 1>}.\n"
            f"Food: {food_name}"
        )
        try:
            start = time.time()
            resp = self._client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            ms = int((time.time() - start) * 1000)
            text = (resp.choices[0].message.content or "").strip().upper()

            usage = getattr(resp, "usage", None)
            if usage:
                self.input_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
                self.output_tokens += int(getattr(usage, "completion_tokens", 0) or 0)

            try:
                data = json.loads(text)
                diet = str(data.get("diet", "")).lower()
                confidence = float(data.get("confidence", 0.0))
            except Exception:
                diet = text.strip().lower()
                confidence = None

            if diet in {"vegan", "vegetarian", "omnivore"}:
                log.info(
                    "llm.classify",
                    food=food_name,
                    result=diet,
                    confidence=confidence,
                    ms=ms,
                )
                return diet, confidence

            log.warning("llm.unexpected_label", got=text)
            return None, None

        except Exception as e:
            log.warning("llm.error.classify", error=str(e))
            return None
