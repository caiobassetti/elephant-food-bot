import io
from decimal import Decimal

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from django.shortcuts import render, redirect
from django.core.management import call_command
from django.db.models import Count, Sum
from django.http import HttpResponse
import matplotlib.pyplot as plt

from .models import UserProfile, Conversation

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

    context = {
        "rows": rows,
        "totals": totals,
        "selected_run_ids": run_ids,
        "selected_diets": diets,
        "options_run_ids": options_run_ids,
        "options_diets": options_diets,
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
