import os
from django.core.asgi import get_asgi_application

# Set Django settings module FIRST
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cc_marketers.settings')

# Initialize Django ASGI application early to ensure AppRegistry is populated
# before importing routing modules that use Django models
django_asgi_app = get_asgi_application()

# NOW import routing modules (after Django is fully set up)
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator

import chat.routing
import notifications.routing  # ← added

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                chat.routing.websocket_urlpatterns +
                notifications.routing.websocket_urlpatterns  # ← merged
            )
        )
    ),
})