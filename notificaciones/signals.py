from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Notificacion
from .services import crear_notificacion

Usuario = get_user_model()

# Atributo temporal en la instancia para comparar el estado antes/después.
_ESTADO_ANTERIOR = '_notificaciones_estado_cuenta_anterior'

ASUNTO_BLOQUEO = 'Tu cuenta de TECNILED fue bloqueada'


@receiver(pre_save, sender=Usuario)
def recordar_estado_de_la_cuenta(sender, instance, **kwargs):
    """Guarda en la instancia el estado que tenía la cuenta en la base de datos."""
    if not instance.pk:
        setattr(instance, _ESTADO_ANTERIOR, None)
        return

    anterior = (
        sender.objects.filter(pk=instance.pk)
        .values_list('estado_cuenta', flat=True)
        .first()
    )
    setattr(instance, _ESTADO_ANTERIOR, anterior)


@receiver(post_save, sender=Usuario)
def notificar_bloqueo_de_cuenta(sender, instance, created, **kwargs):
    """G1-197: notifica al usuario cuando su cuenta pasa a estado BLOQUEADA.

    Solo se dispara en la transición (antes no estaba bloqueada y ahora sí),
    para no crear una notificación nueva cada vez que se guarda el usuario.
    """
    if instance.estado_cuenta != Usuario.EstadoCuenta.BLOQUEADA:
        return

    estado_anterior = getattr(instance, _ESTADO_ANTERIOR, None)
    if estado_anterior == Usuario.EstadoCuenta.BLOQUEADA:
        return

    if instance.intentos_fallidos >= instance.MAX_INTENTOS:
        motivo = (
            f'después de {instance.MAX_INTENTOS} intentos fallidos '
            'de inicio de sesión'
        )
        recomendacion = (
            'Si no reconoces estos intentos, avisa al administrador para '
            'revisar la seguridad de tu cuenta.'
        )
    else:
        motivo = 'por una acción del administrador'
        recomendacion = (
            'Si no estás de acuerdo con el bloqueo, contacta al administrador.'
        )

    mensaje = (
        f'Tu cuenta fue bloqueada {motivo}. '
        'Para recuperarla, contacta al administrador del sistema y solicita '
        f'la reactivación. {recomendacion}'
    )

    crear_notificacion(
        destinatario=instance,
        tipo=Notificacion.Tipo.BLOQUEO_CUENTA,
        canal=Notificacion.Canal.CORREO,
        mensaje=mensaje,
        asunto=ASUNTO_BLOQUEO,
    )

    # Evita duplicados si el mismo objeto se vuelve a guardar sin recargar.
    setattr(instance, _ESTADO_ANTERIOR, instance.estado_cuenta)
