#!/usr/bin/env bash
set -euo pipefail

# Force prod settings
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.prod}"

# Ensure persistent path exists
mkdir -p /home/data

export PYTHONPATH="/app/app:${PYTHONPATH:-}"

# Migrate on each start
python /app/app/manage.py migrate --noinput

# smoke -> small LLM budget for safe deploy
# live -> larger LLM budget for real usage
EFB_PROFILE="${EFB_PROFILE:-}"
if [[ -z "${EFB_LLM_CALL_BUDGET:-}" ]]; then
  case "${EFB_PROFILE}" in
    smoke)
      # low budget for initial deploy checks
      export EFB_LLM_CALL_BUDGET=5
      ;;
    live)
      # larger cap once you're comfortable
      export EFB_LLM_CALL_BUDGET=200
      ;;
    *)
      # safest default when nothing specified
      export EFB_LLM_CALL_BUDGET=0
      ;;
  esac
fi


# Bootstrap runs only if EFB_BOOTSTRAP=1
if [[ "${EFB_BOOTSTRAP:-}" = "1" ]]; then
  echo "EFB_BOOTSTRAP: starting bootstrap tasks..." >&2
  # Create superuser if missing, generate a password if not provided.
  python - <<'PY'
import os, sys, secrets, string, django
sys.path.append("/app/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE","config.settings.prod"))
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()

u = os.environ.get("DJANGO_SUPERUSER_USERNAME")
e = os.environ.get("DJANGO_SUPERUSER_EMAIL") or "admin@example.com"
p = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

if not u:
    print("EFB_BOOTSTRAP: DJANGO_SUPERUSER_USERNAME not set; skipping superuser.", flush=True)
else:
    if User.objects.filter(username=u).exists():
        print(f"EFB_BOOTSTRAP: superuser '{u}' already exists.", flush=True)
    else:
        if not p:
            alphabet = string.ascii_letters + string.digits
            p = ''.join(secrets.choice(alphabet) for _ in range(16))
            with open("/home/first_admin.txt","w") as f:
                f.write(f"{u}:{p}\n")
            print(f"EFB_BOOTSTRAP: generated password written to /home/first_admin.txt for user '{u}'.", flush=True)
        User.objects.create_superuser(username=u, email=e, password=p)
        print(f"EFB_BOOTSTRAP: superuser '{u}' created.", flush=True)
PY

  # Create/print DRF token for that user (if username provided)
  if [[ -n "${DJANGO_SUPERUSER_USERNAME:-}" ]]; then
    echo "EFB_BOOTSTRAP: creating DRF token for ${DJANGO_SUPERUSER_USERNAME}..." >&2
    # drf_create_token prints the token; tee saves a copy under /home
    python /app/app/manage.py drf_create_token "$DJANGO_SUPERUSER_USERNAME" | tee /home/first_token.txt || true
  fi

  # Seed a few conversations so the API has data
  RUNS="${EFB_BOOTSTRAP_RUNS:-3}"
  echo "EFB_BOOTSTRAP: running simulate_foods --runs=${RUNS}..." >&2
  python /app/app/manage.py simulate_foods --runs="${RUNS}" || true

  echo "EFB_BOOTSTRAP: bootstrap tasks done." >&2
fi


# Run Gunicorn on :8000
exec gunicorn config.wsgi:application \
  --chdir /app/app \
  --bind 0.0.0.0:8000 \
  --workers 3 \
  --timeout 90
