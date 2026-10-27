"""
URL configuration for TECNILED project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    # Redirige /sistema/ directamente a /sistema/respaldos/
    path('sistema/', RedirectView.as_view(pattern_name='respaldos_lista', permanent=False)),
    path('sistema/', include('sistema.urls')),
    path('ayuda/', include('ayuda.urls')),
    path('', include('Usuarios.urls')),
    path('', include('productos.urls')),
    path('', include('compras.urls')),   
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)