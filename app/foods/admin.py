from django.contrib import admin

from .models import UserProfile, Conversation, FavoriteFood, FoodCatalog


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "diet", "run_id", "created_at")
    list_filter = ("diet",)
    search_fields = ("id", "run_id")


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "model", "total_tokens", "estimated_cost_usd", "created_at")
    list_filter = ("role", "model")
    search_fields = ("user__id", "run_id")
    readonly_fields = ("created_at",)


@admin.register(FavoriteFood)
class FavoriteFoodAdmin(admin.ModelAdmin):
    list_display = ("user", "rank", "name_raw", "food_name", "catalog", "created_at")
    list_filter = ("rank",)
    search_fields = ("user__id", "name_raw", "food_name")


@admin.register(FoodCatalog)
class FoodCatalogAdmin(admin.ModelAdmin):
    list_display = ("food_name", "diet", "source", "confidence", "updated_at")
    list_filter = ("diet", "source")
    search_fields = ("food_name",)
