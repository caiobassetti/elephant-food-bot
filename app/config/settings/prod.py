# ruff: noqa: F403, F405
import os

from .base import *

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost").split(",")

# Security headers
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Static files via WhiteNoise
if "whitenoise.middleware.WhiteNoiseMiddleware" not in MIDDLEWARE:
    _mw = list(MIDDLEWARE)
    try:
        idx = _mw.index("django.middleware.security.SecurityMiddleware")
        _mw.insert(idx + 1, "whitenoise.middleware.WhiteNoiseMiddleware")
    except ValueError:
        _mw.insert(0, "whitenoise.middleware.WhiteNoiseMiddleware")
    MIDDLEWARE = _mw

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
