from django.db import models
import uuid


class DietLabel(models.TextChoices):
    VEGAN = "vegan", "Vegan"
    VEGETARIAN = "vegetarian", "Vegetarian"
    OMNIVORE = "omnivore", "Omnivore"
    UNKNOWN = "unknown", "Unknown"


class MessageRole(models.TextChoices):
    A = "A", "Asker"
    B = "B", "Responder"


class FoodCatalog(models.Model):
    """
    Cache of food names and their diet labels.
    Avoids paying LLM cost for the foods already labeled.
    """
    food_name = models.CharField(max_length=120, unique=True)
    diet = models.CharField(
        max_length=12,
        choices=DietLabel.choices,
        default=DietLabel.UNKNOWN
    )
    source = models.CharField(max_length=16, default="static") # static, llm or manual
    confidence = models.FloatField(null=True, blank=True) # When LLM is used
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "food_catalog"
        indexes = [
            models.Index(fields=["food_name"]),
            models.Index(fields=["diet"]),
        ]

    def __str__(self):
        return f"{self.food_name} [{self.diet}]"


class UserProfile(models.Model):
    """
    Generated "user" for the B-side of a conversation run.
    Diet is set after evaluating the top-3 foods in a run.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    diet = models.CharField(
        max_length=12,
        choices=DietLabel.choices,
        default=DietLabel.UNKNOWN
    )
    run_id = models.UUIDField(null=True, blank=True)  # Batch with 100 runs
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_profile"
        indexes = [
            models.Index(fields=["diet"]),
            models.Index(fields=["run_id"]),
        ]

    def __str__(self):
        return f"user:{self.id} diet:{self.diet}"


class Conversation(models.Model):
    """
    Single message in a conversation (either A or B).
    Tokens/costs are stored for accounting.
    """
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=1, choices=MessageRole.choices)
    prompt = models.TextField(blank=True, default="") # What A asked or the prompt used
    response = models.TextField(blank=True, default="") # What B answered (empty for A)
    model = models.CharField(max_length=64, blank=True, default="")

    # Token/costs accounting
    prompt_tokens = models.IntegerField(null=True, blank=True)
    completion_tokens = models.IntegerField(null=True, blank=True)
    total_tokens = models.IntegerField(null=True, blank=True)
    estimated_cost_usd = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True
    )

    run_id = models.UUIDField(null=True, blank=True)  # UserProfile.run_id for filtering
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "conversation"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["role"]),
            models.Index(fields=["run_id"]),
        ]

    def __str__(self):
        return f"{self.role} msg for {self.user_id} @ {self.created_at:%Y-%m-%d %H:%M:%S}"


class FavoriteFood(models.Model):
    """
    Top-3 foods for a given user.
    """
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="foods")
    rank = models.PositiveSmallIntegerField()
    name_raw = models.CharField(max_length=120)
    food_name = models.CharField(max_length=120, blank=True, default="")
    catalog = models.ForeignKey(FoodCatalog, null=True, blank=True, on_delete=models.SET_NULL)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "favorite_food"
        constraints = [
            models.UniqueConstraint(fields=["user", "rank"], name="unique_food_rank_per_user")
        ]
        indexes = [
            models.Index(fields=["user", "rank"]),
        ]

    def __str__(self):
        return f"{self.user_id} #{self.rank} {self.name_raw}"
