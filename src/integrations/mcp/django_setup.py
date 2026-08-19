import os


def setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

    import django
    from django.apps import apps

    if not apps.ready:
        django.setup()
