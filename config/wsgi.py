"""
WSGI config for the SalvageMe backend.

On PythonAnywhere, the web app's WSGI configuration file (edited from the
"Web" tab) should import `application` from this module after setting
DJANGO_SETTINGS_MODULE to `config.settings.prod` and adding the project
directory to sys.path. See README.md -> "Deploying to PythonAnywhere".
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_wsgi_application()
