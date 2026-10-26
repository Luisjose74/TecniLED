from django.core.mail import send_mail

from .models import Notificacion


def crear_notificacion(
    *,
    destinatario,
    tipo,
    mensaje,
    canal=Notificacion.Canal.INTERNA,
    asunto=None,
):
    """Crea una notificación y, si el canal es correo, la envía por email.

    El envío nunca debe romper el flujo que originó la alerta (por ejemplo,
    el bloqueo de una cuenta), por eso se usa ``fail_silently`` y se protege
    con un try/except.
    """
    notificacion = Notificacion.objects.create(
        destinatario=destinatario,
        tipo=tipo,
        canal=canal,
        mensaje=mensaje,
    )

    if canal == Notificacion.Canal.CORREO:
        try:
            send_mail(
                asunto or 'Notificación de TECNILED',
                mensaje,
                None,
                [destinatario.email],
                fail_silently=True,
            )
        except Exception:
            # La notificación interna ya quedó guardada; un fallo de correo
            # no debe interrumpir el inicio de sesión ni la vista.
            pass

    return notificacion
