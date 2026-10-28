from .models import Notificacion


def notificaciones(request):
    """Deja disponibles la campana y el contador en todas las plantillas."""
    usuario = getattr(request, 'user', None)
    if usuario is None or not usuario.is_authenticated:
        return {}

    notificaciones_usuario = Notificacion.objects.filter(destinatario=usuario)
    return {
        'notificaciones_sin_leer': notificaciones_usuario.filter(leido=False).count(),
        'ultimas_notificaciones': notificaciones_usuario[:6],
    }
