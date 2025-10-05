# PATH import
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

DJANGO_APP_DIR = REPO_ROOT / "app"
MANAGE_PATH = DJANGO_APP_DIR / "manage.py"

# Structure check
if not MANAGE_PATH.is_file() or not (DJANGO_APP_DIR / "config").is_dir():
    raise RuntimeError(
        "Expected Django app at 'app/' with 'manage.py' and 'config/' package."
    )

# Put the Django app dir at the front of sys.path so 'import config' works
sys.path.insert(0, str(DJANGO_APP_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")


import uuid
from contextlib import contextmanager

import pytest
from django.conf import settings
from django.db import connections, models
from django.test import Client
from django.utils import timezone

# some tests don't require API client
try:
    from rest_framework.test import APIClient
except Exception:
    APIClient = None

# scope='session' -> runs once for the entire pytest run
# autouse=True -> runs even if no test explicitly requests it
@pytest.fixture(scope="session", autouse=True)
# Override DATABASES to use sqlite DB for tests
def _force_sqlite_db():
    settings.DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "ATOMIC_REQUESTS": False,
    }
    # Ensure connections pick up modified settings
    for alias in connections:
        try:
            connections[alias].close()
        except Exception:
            pass
    yield


@pytest.fixture
# Returns either API client or plain django client
def api_client():
    if APIClient is not None:
        return APIClient()
    return Client()


# Generate valid default per field type
def _default_for_field(field):
    if isinstance(field,
        models.CharField |
        models.TextField
    ):
        return "x"
    if isinstance(field, models.BooleanField):
        return False
    if isinstance(field,
        models.IntegerField |
        models.BigIntegerField |
        models.SmallIntegerField |
        models.AutoField
    ):
        return 0
    if isinstance(field, models.FloatField):
        return 0.0
    if isinstance(field, models.DecimalField):
        return 0
    if isinstance(field, models.UUIDField):
        return uuid.uuid4()
    if isinstance(field, models.DateTimeField):
        return timezone.now()
    if isinstance(field, models.DateField):
        return timezone.now().date()
    if isinstance(field, models.JSONField):
        return {}
    return None


# Decorator allows it to be used with 'with _reentrancy_guard():'
# to guarantee cleanup even in case of exception
@contextmanager
def _reentrancy_guard(seen):
    # Ensures that seen is cleared no matter what (success or exception)
    try:
        yield
    finally:
        seen.clear()

# Keeps a seen set of models it is currently constructing
# to prevent infinite recursion in cyclic relations (A -> B -> A).
def build_instance(Model, **overrides):
    seen = set()

    def _make(mdl):
        if mdl in seen:
            # Break cycle by returning an instance with just a PK when possible
            inst = mdl()
            if hasattr(inst, "pk") and inst.pk is None:
                pass
            return inst
        seen.add(mdl)

        data = {}
        for f in mdl._meta.get_fields():
            if f.auto_created and not f.concrete:
                # Skips reverse/auto-created relations
                continue
            if getattr(f, "primary_key", False):
                # Skips primary keys
                continue
            if f.name in overrides:
                data[f.name] = overrides[f.name]
                # If an override was used (user=user), it uses that
                continue
            if hasattr(f, "default") and f.default != models.NOT_PROVIDED:
                # If a field has a default, it’s safe to skip
                continue
            if getattr(f, "null", False):
                # If a field is nullable, it’s safe to skip
                continue
            if isinstance(f, models.ForeignKey):
                # For ForeignKey fields, it builds the related instance first and assigns it
                rel = f.remote_field.model
                rel_inst = _make(rel)
                rel_inst.save()
                data[f.name] = rel_inst
            else:
                # For scalar fields, it supplies an appropriate type
                val = _default_for_field(f)
                if val is not None:
                    data[f.name] = val
        inst = mdl(**data)
        inst.save()
        return inst

    with _reentrancy_guard(seen):
        return _make(Model)
