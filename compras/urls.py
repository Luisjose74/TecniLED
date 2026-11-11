from django.urls import path

from . import views

urlpatterns = [
    path('compras/', views.ordenes_lista, name='ordenes_lista'),
    path('compras/crear/', views.crear_orden, name='crear_orden'),
    path('compras/exportar/', views.exportar_ordenes, name='exportar_ordenes'),
    path('compras/<int:pk>/', views.orden_detalle, name='orden_detalle'),
    path('compras/<int:pk>/editar/', views.editar_orden, name='editar_orden'),
    path('compras/<int:pk>/remision/', views.adjuntar_remision, name='adjuntar_remision'),
]
