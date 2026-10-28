from django.apps import AppConfig


class NotificacionesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'notificaciones'
    verbose_name = 'Notificaciones'

    def ready(self):
        # Registra las señales de bloqueo de cuenta (G1-197).
        from . import signals  # noqa: F401
