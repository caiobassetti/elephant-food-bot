import os, time
import structlog

log = structlog.get_logger(__name__)

DRY_RUN = os.getenv("DRY_RUN", "1") == "1"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Price in USD per 1K tokens
PRICE_PER_1K_INPUT = float(os.getenv("OPENAI_PRICE_PER_1K_INPUT", "0.150"))
PRICE_PER_1K_OUTPUT = float(os.getenv("OPENAI_PRICE_PER_1K_OUTPUT", "0.600"))

class OpenAIClient:
    def __init__(self, dry_run=None):
        self.dry_run = DRY_RUN if dry_run is None else bool(dry_run)
        self.input_tokens = 0
        self.output_tokens = 0
        self._client = None
        if not self.dry_run:
            try:
                # Import here to avoid dev and CI crashes
                from openai import OpenAI
                self._client = OpenAI(api_key=OPENAI_API_KEY)
            except Exception as e:
                log.warning("openai_import_failed", error=str(e))

    def cost_usd(self):
        return (self.input_tokens/1000.0) * PRICE_PER_1K_INPUT + \
               (self.output_tokens/1000.0) * PRICE_PER_1K_OUTPUT

    def classify_food_diet(self, food_name):
        if self.dry_run or not OPENAI_API_KEY or not self._client:
            log.info("llm.skip_dry_run", reason="dry-run or no api", food=food_name)
            return None

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
                temperature=0
            )
            ms = int((time.time() - start) * 1000)
            text = (resp.choices[0].message.content or "").strip().upper()

            usage = getattr(resp, "usage", None)
            if usage:
                self.input_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
                self.output_tokens += int(getattr(usage, "completion_tokens", 0) or 0)

            if text in {"VEGAN","VEGETARIAN","OMNIVORE"}:
                log.info("llm.classify", food=food_name, result=text, ms=ms)
                return text
            log.warning("llm.unexpected_label", got=text)
            return None
        except Exception as e:
            log.warning("llm.error", error=str(e))
            return None
