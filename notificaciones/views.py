from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Notificacion


@login_required
def lista(request):
    """Listado de notificaciones del usuario autenticado (G1-203)."""
    notificaciones_usuario = Notificacion.objects.filter(destinatario=request.user)
    sin_leer = notificaciones_usuario.filter(leido=False).count()

    paginador = Paginator(notificaciones_usuario, 15)
    pagina = paginador.get_page(request.GET.get('page'))

    # Los clientes ven la página con el header de la tienda; el personal
    # interno la ve dentro del panel de administración.
    plantilla = (
        'notificaciones/lista.html'
        if request.user.rol == 'cliente'
        else 'notificaciones/lista_admin.html'
    )

    return render(request, plantilla, {
        'pagina': pagina,
        'sin_leer': sin_leer,
        'total': paginador.count,
    })


@login_required
@require_POST
def marcar_leida(request, pk):
    notificacion = get_object_or_404(
        Notificacion, pk=pk, destinatario=request.user
    )
    notificacion.marcar_leida()
    messages.success(request, 'Notificación marcada como leída.')
    return redirect('notificaciones_lista')


@login_required
@require_POST
def marcar_todas(request):
    actualizadas = Notificacion.objects.filter(
        destinatario=request.user, leido=False
    ).update(leido=True)

    if not actualizadas:
        messages.info(request, 'No tienes notificaciones sin leer.')
    elif actualizadas == 1:
        messages.success(request, 'Se marcó 1 notificación como leída.')
    else:
        messages.success(
            request,
            f'Se marcaron {actualizadas} notificaciones como leídas.',
        )

    return redirect('notificaciones_lista')
