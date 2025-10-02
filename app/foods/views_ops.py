from __future__ import annotations
import os
from django.http import JsonResponse
from django.core.management import call_command
from django.views.decorators.csrf import csrf_exempt

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import TokenAuthentication, BasicAuthentication
from rest_framework.permissions import IsAdminUser

@csrf_exempt
@api_view(["POST"])
@authentication_classes([TokenAuthentication, BasicAuthentication])
@permission_classes([IsAdminUser])
def run_simulation(request):
    """
    Trigger the simulate_foods management command.

    Body (JSON):
      - runs: int (default 3)
      - budget: int | null (optional, temporarily overrides EFB_LLM_CALL_BUDGET)

    Auth:
      - DRF Token or Basic auth for a staff/superuser.
    """
    try:
        runs = int(request.data.get("runs", 3))
    except Exception:
        return JsonResponse({"error": "runs must be an integer"}, status=400)

    budget = request.data.get("budget", None)
    old_budget = os.environ.get("EFB_LLM_CALL_BUDGET")

    try:
        if budget is not None:
            os.environ["EFB_LLM_CALL_BUDGET"] = str(int(budget))
        # hand control to your management command
        call_command("simulate_foods", runs=str(runs))
        return JsonResponse({"status": "ok", "runs": runs, "budget": os.environ.get("EFB_LLM_CALL_BUDGET")})
    except Exception as e:
        return JsonResponse({"status": "error", "detail": str(e)}, status=500)
    finally:
        # put the budget back the way we found it
        if budget is not None:
            if old_budget is None:
                os.environ.pop("EFB_LLM_CALL_BUDGET", None)
            else:
                os.environ["EFB_LLM_CALL_BUDGET"] = old_budget
