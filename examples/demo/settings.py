SECRET_KEY = "demo-only"
DEBUG = True
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "shop",
]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
ROOT_URLCONF = "urls"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
