from django.conf import settings
from django.db import models


class Notificacion(models.Model):
    """Notificación persistente para un usuario (G1-10 - Gestión de notificaciones).

    Se usa tanto para las alertas de seguridad (G1-197 y G1-203) como para las
    notificaciones internas del resto de historias de la épica.
    """

    class Tipo(models.TextChoices):
        GENERAL = 'general', 'General'
        BLOQUEO_CUENTA = 'bloqueo_cuenta', 'Bloqueo de cuenta'
        ACCESO_DENEGADO = 'acceso_denegado', 'Acceso denegado'
        SEGURIDAD = 'seguridad', 'Seguridad'
        PROMOCION = 'promocion', 'Promoción'

    class Canal(models.TextChoices):
        INTERNA = 'interna', 'Interna'
        CORREO = 'correo', 'Correo'
        WHATSAPP = 'whatsapp', 'WhatsApp'

    destinatario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notificaciones',
        verbose_name='destinatario',
    )
    tipo = models.CharField(
        max_length=30, choices=Tipo.choices, default=Tipo.GENERAL
    )
    canal = models.CharField(
        max_length=20, choices=Canal.choices, default=Canal.INTERNA
    )
    mensaje = models.TextField()
    leido = models.BooleanField(default=False)
    fecha_envio = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha_envio']
        indexes = [
            models.Index(fields=['destinatario', 'leido']),
        ]
        verbose_name = 'notificación'
        verbose_name_plural = 'notificaciones'

    def __str__(self):
        estado = 'leída' if self.leido else 'sin leer'
        return f'{self.get_tipo_display()} para {self.destinatario} ({estado})'

    def marcar_leida(self):
        if not self.leido:
            self.leido = True
            self.save(update_fields=['leido'])
