import json
import os
import re
import time

import structlog

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

    @staticmethod # To bypass `self.`
    # Parse top-3 food list
    def _parse_three_foods(text):
        s = (text or "").strip()
        # Try json
        try:
            data = json.loads(s)
            if isinstance(data, list):
                items = [str(x).strip() for x in data if str(x).strip()]
                if len(items) == 3:
                    return items
        except Exception:
            pass

        # Try comma-separated
        parts = [p.strip() for p in re.split(r"[,\n;]", s) if p.strip()]
        if len(parts) == 3:
            return parts

        raise ValueError(f"Expected exactly 3 foods; got: {s[:120]}")


    # Send prompt and expect 3 foods back
    def ask_top_three_favorite_foods(self, composed_prompt):
        self._consume_budget("ask_top_three_favorite_foods")

        system = (
            "You are a concise assistant. "
            "Return exactly three food names, short strings. "
            "Prefer single dishes or items. "
            "Format the answer as a JSON array of three strings."
        )
        try:
            start = time.time()
            resp = self._client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": composed_prompt},
                ],
                temperature=0.2,
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
            log.warning("llm.error.top3", error=str(e))
            raise

    # Classify a single food into VEGAN / VEGETARIAN / OMNIVORE
    def classify_food_diet(self, food_name):
        self._consume_budget("classify_food_diet")

        prompt = (
            "Classify the single food item below into one label:\n"
            "- VEGAN: contains no animal products.\n"
            "- VEGETARIAN: may include dairy/eggs, but no meat/fish.\n"
            "- OMNIVORE: includes meat or fish.\n"
            f"Food: {food_name}\n"
            "Return ONLY the label: vegan, vegetarian, or omnivore."
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

            if text in {"VEGAN", "VEGETARIAN", "OMNIVORE"}:
                log.info("llm.classify", food=food_name, result=text, ms=ms)
                return text
            log.warning("llm.unexpected_label", got=text)
            return None
        except Exception as e:
            log.warning("llm.error.classify", error=str(e))
            return None
