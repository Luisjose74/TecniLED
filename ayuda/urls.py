from django.urls import path

from . import views

urlpatterns = [
    path('', views.ayuda, name='ayuda'),
]
