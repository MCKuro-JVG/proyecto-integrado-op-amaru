from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        User=get_user_model()
        try:
            user=User.objects.get(email__iexact=username) if '@' in (username or '') else User.objects.get(username=username)
        except (User.DoesNotExist,User.MultipleObjectsReturned):
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user): return user


from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.http import HttpResponse


class LimitedLoginView(LoginView):
    """Comparte el límite con la API; no existe un acceso HTML alternativo sin límite."""
    def post(self,request,*args,**kwargs):
        key='login:'+request.META.get('REMOTE_ADDR','')
        count=cache.get(key,0)
        if count>=10:return HttpResponse('Demasiados intentos. Espere cinco minutos.',status=429)
        cache.set(key,count+1,300)
        return super().post(request,*args,**kwargs)
    def form_valid(self,form):
        cache.delete('login:'+self.request.META.get('REMOTE_ADDR',''))
        return super().form_valid(form)
