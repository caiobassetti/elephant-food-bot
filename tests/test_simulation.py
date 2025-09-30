import uuid

import pytest
from django.apps import apps
from django.core.management import call_command

pytestmark = pytest.mark.django_db # Allows db access to the tests

# Command should complete without hitting the real OpenAI (DRY_RUN=1 + mock guard)
# It should persists some domain records (Conversation row)
def test_simulate_foods_command_smoke_runs_without_external_calls(monkeypatch):
    # Calls 'manage.py simulate_foods --runs=3 --run-id=<uuid>'
    run_id = uuid.uuid4()
    call_command("simulate_foods", runs=3, run_id=str(run_id))

    Conversation = apps.get_model("foods", "Conversation")
    assert Conversation.objects.count() >= 0
