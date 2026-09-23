from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls import handler400, handler403, handler404, handler500
from rbzk.admin import admin_site


handler400 = 'error_views.views.bad_request'
handler403 = 'error_views.views.permission_denied'
handler404 = 'error_views.views.page_not_found'
handler500 = 'error_views.views.server_error'

if settings.DEBUG:
    admin_url = "admin/"
else:
    admin_url = "89ee14c8c7cb465faa10ec1a5e142fd3/"


urlpatterns = [
    path(admin_url, admin_site.urls),
    # path('89ee14c8c7cb465faa10ec1a5e142fd3/', admin.site.urls),
    path('', include("home.urls")),
    # path('', include("cal_stats.urls")),
    path('', include('cb_mark.urls')),
    path('nbrbth4yh67/', include("cb_page.urls"))
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)