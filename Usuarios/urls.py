from django.urls import path
from . import views

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('creditos/', views.creditos, name='creditos'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('usuarios/', views.usuarios_lista, name='usuarios_lista'),
    path('usuarios/crear/', views.crear_usuario, name='crear_usuario'),
    path('usuarios/<int:usuario_id>/editar-rol/', views.editar_rol, name='editar_rol'),
    path('recuperar-contrasena/', views.recuperar_contrasena, name='recuperar_contrasena'),
    path('usuarios/<int:usuario_id>/', views.usuario_detalle, name='usuario_detalle'),
    path('usuarios/<int:usuario_id>/inactivar/', views.inactivar_usuario, name='inactivar_usuario'),

]