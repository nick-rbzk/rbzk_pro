from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls import handler400, handler403, handler404, handler500

handler400 = 'your_app.views.bad_request'
handler403 = 'your_app.views.permission_denied'
handler404 = 'your_app.views.page_not_found'
handler500 = 'your_app.views.server_error'

urlpatterns = [
    path('89ee14c8c7cb465faa10ec1a5e142fd3/', admin.site.urls),
    path('', include("home.urls")),
    path('', include("cal_stats.urls")),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# For testing (only in development)
if settings.DEBUG:
    urlpatterns += [
        path('400/', lambda request: HttpResponseBadRequest(render(request, '400.html'))),
        path('403/', lambda request: HttpResponseForbidden(render(request, '403.html'))),
        path('404/', lambda request: HttpResponseNotFound(render(request, '404.html'))),
        path('500/', lambda request: HttpResponseServerError(render(request, '500.html'))),
    ]