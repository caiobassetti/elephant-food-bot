# PATH settings
import os
import sys
from pathlib import Path

# Find repo root (folder containing /tests/)
THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[1]

# Find the Django app dir
DJANGO_APP_DIR = None
for mp in REPO_ROOT.rglob("manage.py"):
    candidate = mp.parent
    if (candidate / "config").is_dir():
        DJANGO_APP_DIR = candidate
        break

if DJANGO_APP_DIR is None:
    for cfg in REPO_ROOT.rglob("config/__init__.py"):
        DJANGO_APP_DIR = cfg.parent.parent
        break

if DJANGO_APP_DIR is None:
    raise RuntimeError(
        "Could not locate Django app directory. "
        "Expected to find 'manage.py' and a 'config/' package somewhere under the repo."
    )

# Put the Django app dir at the front of sys.path so 'import config' works
sys.path.insert(0, str(DJANGO_APP_DIR))

# Ensure DJANGO_SETTINGS_MODULE is set
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

import uuid
from contextlib import contextmanager

import pytest
from django.conf import settings
from django.db import connections, models
from django.test import Client
from django.utils import timezone

try:
    from rest_framework.test import APIClient
except Exception:
    APIClient = None


@pytest.fixture(scope="session", autouse=True)
def _force_sqlite_db():
    # Override DATABASES to use sqlite DB for tests
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
def api_client():
    if APIClient is not None:
        return APIClient()
    return Client()


def _default_for_field(field):
    # Generate valid default per field type
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
                continue # Skips reverse/auto-created relations
            if getattr(f, "primary_key", False):
                continue # Skips primary keys
            if f.name in overrides:
                data[f.name] = overrides[f.name]
                continue # If an override was used (user=user), it uses that
            if hasattr(f, "default") and f.default != models.NOT_PROVIDED:
                continue # If a field has a default, it’s safe to skip
            if getattr(f, "null", False):
                continue # If a field is nullable, it’s safe to skip
            if isinstance(f, models.ForeignKey):
                # For ForeignKey fields, it builds the related instance first and assigns it
                rel = f.remote_field.model
                rel_inst = _make(rel)
                rel_inst.save()
                data[f.name] = rel_inst
            else:
                val = _default_for_field(f) # For scalar fields, it supplies an appropriate type
                if val is not None:
                    data[f.name] = val
        inst = mdl(**data)
        inst.save()
        return inst

    with _reentrancy_guard(seen):
        return _make(Model)
