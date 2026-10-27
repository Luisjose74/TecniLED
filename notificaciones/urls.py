from django.urls import path

from . import views

urlpatterns = [
    path('', views.lista, name='notificaciones_lista'),
    path('marcar-todas/', views.marcar_todas, name='notificaciones_marcar_todas'),
    path(
        '<int:pk>/marcar-leida/',
        views.marcar_leida,
        name='notificacion_marcar_leida',
    ),
]
