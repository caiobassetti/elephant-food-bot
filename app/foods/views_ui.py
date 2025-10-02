import io
from django.shortcuts import render, redirect
from django.core.management import call_command
from django.db.models import Count, Sum
from django.http import HttpResponse
import matplotlib.pyplot as plt

from .models import UserProfile, FavoriteFood, Conversation, DietLabel

def dashboard(request):
    run_id = request.GET.get("run_id")
    diet = request.GET.get("diet")

    qs_users = UserProfile.objects.all()
    if run_id:
        qs_users = qs_users.filter(run_id=run_id)
    if diet:
        qs_users = qs_users.filter(diet=diet)

    # totals
    totals = Conversation.objects.aggregate(
        total_tokens=Sum("total_tokens"),
        total_cost=Sum("estimated_cost_usd"),
    )

    # prepare rows for table
    rows = []
    for u in qs_users.prefetch_related("foods"):
        foods = [f.food_name for f in u.foods.all().order_by("rank")]
        conv = Conversation.objects.filter(user=u).order_by("created_at").last()
        rows.append({
            "run_id": u.run_id,
            "user_id": u.id,
            "diet": u.diet,
            "foods": foods,
            "tokens": conv.total_tokens if conv else None,
            "cost": conv.estimated_cost_usd if conv else None,
        })

    context = {
        "rows": rows,
        "totals": totals,
        "filter_run_id": run_id or "",
        "filter_diet": diet or "",
    }
    return render(request, "foods/dashboard.html", context)


def simulate(request):
    count = int(request.GET.get("count", "10"))
    call_command("simulate_foods", runs=count)
    return redirect("/ui/?refresh=1")

def diets_png(request):
    run_id = request.GET.get("run_id")
    diet = request.GET.get("diet")

    qs = UserProfile.objects.all()
    if run_id:
        qs = qs.filter(run_id=run_id)
    if diet:
        qs = qs.filter(diet=diet)

    counts = qs.values("diet").annotate(c=Count("id"))

    labels = [c["diet"] for c in counts]
    values = [c["c"] for c in counts]

    fig, ax = plt.subplots()
    ax.pie(values, labels=labels, autopct="%1.1f%%")
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    return HttpResponse(buf.getvalue(), content_type="image/png")
