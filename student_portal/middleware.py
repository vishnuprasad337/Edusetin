from django.contrib.auth import logout
from .models import UserSession

class SingleSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and hasattr(request.user, 'student'):
            try:
                db_session = UserSession.objects.get(user=request.user)
                if request.session.get('session_key') != db_session.session_key:
                    logout(request)
            except UserSession.DoesNotExist:
                pass
        return self.get_response(request)