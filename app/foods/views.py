from __future__ import annotations

import io
import os

from django.core.management import call_command
from django.db.models import Count, Prefetch, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render

from rest_framework.authentication import BasicAuthentication, TokenAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .models import Conversation, DietLabel, FavoriteFood, UserProfile
from .serializers import VegUserSerializer


def dashboard(request):
    run_ids = request.GET.getlist("run_id")
    diets   = request.GET.getlist("diet")

    # Queryset for users
    qs_users = UserProfile.objects.all()
    if "run_id" in request.GET and run_ids:
        qs_users = qs_users.filter(run_id__in=run_ids)
    if "diet" in request.GET and diets:
        qs_users = qs_users.filter(diet__in=diets)

    # Totals
    agg = Conversation.objects.aggregate(
        total_tokens=Sum("total_tokens"),
        total_cost=Sum("estimated_cost_usd"),
    )
    totals = {
        "total_tokens": agg["total_tokens"] or 0,
        "total_cost": round(float(agg["total_cost"] or 0), 4),
    }

    # Options for dropdowns
    run_ids_all_qs = UserProfile.objects.exclude(run_id__isnull=True).values_list("run_id", flat=True)
    options_run_ids = sorted(set(str(x) for x in run_ids_all_qs), reverse=True)

    diets_all_qs = UserProfile.objects.values_list("diet", flat=True)
    options_diets = sorted(set(diets_all_qs))

    # Table
    rows = []
    for u in qs_users.prefetch_related("foods").order_by("-created_at"):
        foods = [f.food_name for f in u.foods.all().order_by("rank")]
        conv = Conversation.objects.filter(user=u).order_by("-created_at").first()
        rows.append({
            "run_id": u.run_id,
            "user_id": u.id,
            "diet": u.diet,
            "foods": foods,
            "tokens": getattr(conv, "total_tokens", None),
            "cost": getattr(conv, "estimated_cost_usd", None),
        })

    # Seen foods
    seen = []
    seen_keys = set()

    fav_qs = (
        FavoriteFood.objects
        .filter(user__in=qs_users)
        .select_related("catalog")
        .order_by("catalog__food_name", "food_name")
    )

    for f in fav_qs:
        cat = f.catalog
        key = (cat.id if cat else f.food_name.lower())
        if key in seen_keys:
            continue
        seen_keys.add(key)

        name = getattr(cat, "food_name", f.food_name)
        diet = getattr(cat, "diet", "unknown")
        source = getattr(cat, "source", None)
        confidence = getattr(cat, "confidence", None)

        if source == "seed":
            confidence_display = "Seed"
        else:
            confidence_display = f"{confidence:.2f}" if (confidence is not None) else "—"

        seen.append({
            "food_name": name,
            "diet": diet,
            "confidence_display": confidence_display,
        })


    context = {
        "rows": rows,
        "totals": totals,
        "selected_run_ids": run_ids,
        "selected_diets": diets,
        "options_run_ids": options_run_ids,
        "options_diets": options_diets,
        "seen_foods": seen,
    }
    return render(request, "foods/dashboard.html", context)

def simulate(request):
    count = int(request.GET.get("count", "10"))
    call_command("simulate_foods", runs=count)
    return redirect("/ui/")

def diets_png(request):
    run_ids = request.GET.getlist("run_id")
    diets   = request.GET.getlist("diet")

    qs = UserProfile.objects.all()
    if "run_id" in request.GET and run_ids:
        qs = qs.filter(run_id__in=run_ids)
    if "diet" in request.GET and diets:
        qs = qs.filter(diet__in=diets)

    counts = qs.values("diet").annotate(c=Count("id")).order_by("-c")
    labels = [c["diet"] for c in counts] or ["no data"]
    values = [c["c"] for c in counts] or [1]

    # Pie chart
    fig, ax = plt.subplots(figsize=(4.2, 4.2))
    ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
    ax.axis("equal")

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return HttpResponse(buf.getvalue(), content_type="image/png")

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def veg_users_view(request):
    # One-to-one query with JOIN to pull 'catalog' relation (each food has it's catalog info)
    fav_qs = FavoriteFood.objects.select_related("catalog").order_by("pk")

    qs = (
        UserProfile.objects
        .filter(diet__in=[DietLabel.VEGAN, DietLabel.VEGETARIAN])
        # Many-to-many (customers have multiple food favorites)
        .prefetch_related(Prefetch("foods", queryset=fav_qs))
    )

    data = []
    for user in qs:
        favs = list(user.foods.all())
        top3 = [f.food_name for f in favs]
        data.append({
            "user_id": user.pk,
            "run_id": user.run_id,
            "diet": user.diet,
            "top3": top3,
        })

    ser = VegUserSerializer(data=data, many=True)
    ser.is_valid(raise_exception=True)
    return Response(ser.data)


@api_view(["POST"])
@authentication_classes([TokenAuthentication, BasicAuthentication])
@permission_classes([IsAdminUser])
def run_simulation(request):
    # Trigger the simulate_foods management command
    try:
        runs = int(request.data.get("runs", 3))
    except Exception:
        return JsonResponse({"error": "runs must be an integer"}, status=400)

    budget = request.data.get("budget", None)
    old_budget = os.environ.get("EFB_LLM_CALL_BUDGET")

    try:
        if budget is not None:
            os.environ["EFB_LLM_CALL_BUDGET"] = str(int(budget))

        call_command("simulate_foods", runs=str(runs))
        return JsonResponse({"status": "ok", "runs": runs, "budget": os.environ.get("EFB_LLM_CALL_BUDGET")})
    except Exception as e:
        return JsonResponse({"status": "error", "detail": str(e)}, status=500)
    finally:

        if budget is not None:
            if old_budget is None:
                os.environ.pop("EFB_LLM_CALL_BUDGET", None)
            else:
                os.environ["EFB_LLM_CALL_BUDGET"] = old_budget
