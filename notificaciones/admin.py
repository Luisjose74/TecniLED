from django.contrib import admin

from .models import Notificacion


@admin.register(Notificacion)
class NotificacionAdmin(admin.ModelAdmin):
    list_display = ('destinatario', 'tipo', 'canal', 'leido', 'fecha_envio')
    list_filter = ('tipo', 'canal', 'leido')
    search_fields = ('destinatario__email', 'mensaje')
    date_hierarchy = 'fecha_envio'
    readonly_fields = ('fecha_envio',)
    ordering = ('-fecha_envio',)
