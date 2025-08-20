from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.tasks.urls')),
    path('users/', include('apps.users.urls')),
    path('wallets/', include('apps.wallets.urls')),
    path('referrals/', include('apps.referrals.urls')),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
