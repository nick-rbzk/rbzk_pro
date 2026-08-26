from django.utils.deprecation import MiddlewareMixin

class DisableGZipForSSEMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.path.startswith('/trade-dash'):
            request.META['HTTP_ACCEPT_ENCODING'] = ''
        return None