from django.db.models import Q
from django.shortcuts import render

from .models import PreguntaFrecuente


def ayuda(request):
    # Página pública: la puede ver cualquier persona, por eso NO lleva @login_required
    busqueda = request.GET.get('q', '').strip()

    # Solo las preguntas activas
    preguntas = PreguntaFrecuente.objects.filter(activa=True)

    # Si escribió algo en el buscador, filtrar por pregunta o respuesta
    if busqueda:
        preguntas = preguntas.filter(
            Q(pregunta__icontains=busqueda) | Q(respuesta__icontains=busqueda)
        )

    # El personal interno ve la ayuda dentro del panel; los clientes, en la tienda
    if request.user.is_authenticated and request.user.rol != 'cliente':
        plantilla_base = 'admin_base.html'
    else:
        plantilla_base = 'base.html'

    return render(request, 'ayuda/ayuda.html', {
        'preguntas': preguntas,
        'busqueda': busqueda,
        'plantilla_base': plantilla_base,
    })

# Create your views here.
