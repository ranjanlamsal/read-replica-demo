from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env only in local dev.
# Inside Docker, compose injects env vars directly.
if not Path("/.dockerenv").exists():
    load_dotenv(BASE_DIR / ".env")
SECRET_KEY = 'django-insecure-uwq8f2^gsphi+y5608nxy-1i$uf4$iu!ufv$ob1u4y)$wj04wt'
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'library'
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }
# ──────────────────────────────────────────────────────────
# DATABASE CONFIGURATION
#
# Two connections are defined:
#   'default' → master (PRIMARY)  — Django writes here
#   'replica' → replica (STANDBY) — Django reads from here
#
# The DATABASE_ROUTERS setting tells Django to consult
# PrimaryReplicaRouter before every DB operation.
# ──────────────────────────────────────────────────────────

def _db_config(host, port_env="REPLICA_PORT", default_port="5432"):
    """Build a database config dict for a given host."""
    return {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": host,
        "PORT": os.environ.get(port_env, default_port),
        "NAME": os.environ.get("DB_NAME", "myapp"),
        "USER": os.environ.get("DB_USER", "postgres"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "postgres"),
        "OPTIONS": {"connect_timeout": 5},
    }

# Parse comma-separated replica hostnames from environment
# e.g. REPLICA_HOSTS=postgres_replica_1,postgres_replica_2,postgres_replica_3
_replica_hosts = [
    h.strip()
    for h in os.environ.get("REPLICA_HOSTS", "").split(",")
    if h.strip()
]

DATABASES = {
    # Master node — receives all INSERT / UPDATE / DELETE
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "library_db"),
        "USER": os.environ.get("DB_USER", "postgres"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "postgres"),
        "HOST": os.environ.get("PRIMARY_HOST", "localhost"),
        "PORT": os.environ.get("PRIMARY_PORT", "5432"),
        "OPTIONS": {"connect_timeout": 5},
    },
    # Replica node — receives all SELECT queries
    # Inside Docker network: port 5432. On host: mapped to 5433.
    # "replica": {
    #     "ENGINE": "django.db.backends.postgresql",
    #     "NAME": os.environ.get("DB_NAME", "library_db"),
    #     "USER": os.environ.get("DB_USER", "postgres"),
    #     "PASSWORD": os.environ.get("DB_PASSWORD", "postgres"),
    #     "HOST": os.environ.get("REPLICA_DB_HOST", "localhost"),
    #     "PORT": os.environ.get("REPLICA_DB_PORT", "5432"),
    #     "OPTIONS": {"connect_timeout": 5},
    #     "TEST": {
    #         # During tests Django will use the default DB only
    #         "MIRROR": "default",
    #     },
    # },
    #adding via loop
}

for i, host in enumerate(_replica_hosts, start=1):
    DATABASES[f"replica_{i}"] = {
        **_db_config(host),
        "TEST": {"MIRROR": "default"},
    }

 
# Register our custom router
DATABASE_ROUTERS = ["config.db_router.PrimaryReplicaRouter"]
 
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = 'static/'

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "loggers": {
        "library": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
