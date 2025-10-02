import base64
import uuid

import pytest
from django.contrib.auth import get_user_model

# Allows db access to the tests
pytestmark = pytest.mark.django_db

API_PATH = "/api/veg-users/"

def _make_token_for(user):
    from rest_framework.authtoken.models import Token
    token, _ = Token.objects.get_or_create(user=user)
    return token

@pytest.fixture
def user_and_password():
    User = get_user_model()
    password = "secret123"
    u = User.objects.create_user(username="apiuser", password=password)
    return u, password

@pytest.fixture
def token_client(api_client, user_and_password):
    user, _ = user_and_password
    token = _make_token_for(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return api_client

@pytest.fixture
def basic_client(api_client, user_and_password):
    user, password = user_and_password
    creds = f"{user.username}:{password}".encode()
    b64 = base64.b64encode(creds).decode("utf-8")
    api_client.credentials(HTTP_AUTHORIZATION=f"Basic {b64}")
    return api_client

def test_auth_required(api_client):
    res = api_client.get(API_PATH)
    assert res.status_code in (401, 403)

def test_schema_and_types(token_client):
    res = token_client.get(API_PATH)
    assert res.status_code == 200
    assert isinstance(res.data, list)
    for item in res.data:
        assert set(item.keys()) == {"user_id", "run_id", "diet", "top3"}
        uuid.UUID(str(item["user_id"]))
        uuid.UUID(str(item["run_id"]))
        assert item["diet"] in {"vegan", "vegetarian"}
        assert isinstance(item["top3"], list)
        assert 1 <= len(item["top3"]) <= 3
        assert all(isinstance(x, str) for x in item["top3"])

def test_token_auth_allows_access(token_client):
    res = token_client.get(API_PATH)
    assert res.status_code == 200

def test_basic_auth_allows_access(basic_client):
    res = basic_client.get(API_PATH)
    assert res.status_code == 200
