from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls import handler400, handler403, handler404, handler500

handler400 = 'error_views.views.bad_request'
handler403 = 'error_views.views.permission_denied'
handler404 = 'error_views.views.page_not_found'
handler500 = 'error_views.views.server_error'

urlpatterns = [
    path('89ee14c8c7cb465faa10ec1a5e142fd3/', admin.site.urls),
    path('', include("home.urls")),
    path('', include("cal_stats.urls")),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)