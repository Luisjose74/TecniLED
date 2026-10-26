from django.urls import path

from . import views

urlpatterns = [
    path('reportes/', views.reportes_inicio, name='reportes_inicio'),
]