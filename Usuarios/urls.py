from django.urls import path
from . import views

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('usuarios/', views.usuarios_lista, name='usuarios_lista'),
    path('usuarios/crear/', views.crear_usuario, name='crear_usuario'),
    path('usuarios/<int:usuario_id>/editar-rol/', views.editar_rol, name='editar_rol'),
    path('recuperar-contrasena/', views.recuperar_contrasena, name='recuperar_contrasena'),
    path('verificar-acceso/', views.verificar_doble_factor, name='verificar_doble_factor'),
    path('verificar-acceso/reenviar/', views.reenviar_doble_factor, name='reenviar_doble_factor'),
    path('mi-seguridad/', views.seguridad_cuenta, name='seguridad_cuenta'),
    path('usuarios/<int:usuario_id>/', views.usuario_detalle, name='usuario_detalle'),
    path('usuarios/<int:usuario_id>/inactivar/', views.inactivar_usuario, name='inactivar_usuario'),
]