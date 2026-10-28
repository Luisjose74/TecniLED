import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser, Group
from django.db import models
from django.utils import timezone

# Permisos por defecto de cada rol. Se pueden ajustar luego en /admin/ -> Grupos.
PERMISOS_POR_ROL = {
    'administrador': ['gestionar_usuarios', 'gestionar_inventario', 'gestionar_compras'],
    'control_inventario': ['gestionar_inventario'],
    'cliente': [],
}


class Usuario(AbstractUser):
    class Rol(models.TextChoices):
        ADMINISTRADOR = 'administrador', 'Administrador'
        CONTROL_INVENTARIO = 'control_inventario', 'Control de inventario'
        CLIENTE = 'cliente', 'Cliente'

    class EstadoCuenta(models.TextChoices):
        ACTIVA = 'activa', 'Activa'
        SUSPENDIDA = 'suspendida', 'Suspendida'
        BLOQUEADA = 'bloqueada', 'Bloqueada'

    MAX_INTENTOS = 3  # G1-128

    email = models.EmailField('correo electrónico', unique=True)
    documento = models.CharField(max_length=20, unique=True, null=True, blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    rol = models.CharField(max_length=20, choices=Rol.choices, default=Rol.CLIENTE)
    estado_cuenta = models.CharField(
        max_length=12, choices=EstadoCuenta.choices, default=EstadoCuenta.ACTIVA
    )
    intentos_fallidos = models.PositiveSmallIntegerField(default=0)  # G1-128

    class Meta(AbstractUser.Meta):
        permissions = [
            ('gestionar_usuarios', 'Puede gestionar usuarios, roles y permisos'),
            ('gestionar_inventario', 'Puede gestionar el inventario'),
            ('gestionar_compras', 'Puede gestionar las compras a proveedores'),
        ]

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        self.username = self.email
        # G1-128: si el admin reactiva una cuenta bloqueada, se reinicia el contador
        if (self.estado_cuenta == self.EstadoCuenta.ACTIVA
                and self.intentos_fallidos >= self.MAX_INTENTOS):
            self.intentos_fallidos = 0
        self.is_active = self.estado_cuenta == self.EstadoCuenta.ACTIVA
        if self.is_superuser:
            self.rol = self.Rol.ADMINISTRADOR
        super().save(*args, **kwargs)
        self.sincronizar_grupo_por_rol()

    def sincronizar_grupo_por_rol(self):
        """Deja al usuario solo en el grupo que corresponde a su rol actual."""
        grupos_de_roles = Group.objects.filter(name__in=[r.label for r in self.Rol])
        self.groups.remove(*grupos_de_roles)
        grupo, _ = Group.objects.get_or_create(name=self.get_rol_display())
        self.groups.add(grupo)

    def __str__(self):
        return self.email


class CodigoRecuperacion(models.Model):
    """Código temporal de un solo uso para recuperar la contraseña (G1-126)
    y para el doble factor de autenticación (G1-127)."""

    VIGENCIA_MINUTOS = 10
    MAX_INTENTOS = 5

    class Proposito(models.TextChoices):
        RECUPERACION = 'recuperacion', 'Recuperación de contraseña'
        DOBLE_FACTOR = 'doble_factor', 'Doble factor de autenticación'

    usuario = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name='codigos_recuperacion'
    )
    codigo_hash = models.CharField(max_length=128)  # el código nunca se guarda en claro
    creado_en = models.DateTimeField(auto_now_add=True)
    expira_en = models.DateTimeField()
    usado = models.BooleanField(default=False)
    intentos = models.PositiveSmallIntegerField(default=0)
    proposito = models.CharField(
        max_length=20, choices=Proposito.choices, default=Proposito.RECUPERACION
    )  # G1-304

    class Meta:
        ordering = ['-creado_en']

    def __str__(self):
        return f'Código de {self.usuario.email} ({self.creado_en:%Y-%m-%d %H:%M})'

    @classmethod
    def generar(cls, usuario, proposito=Proposito.RECUPERACION):
        """Crea un código nuevo e invalida los anteriores del mismo propósito.
        Devuelve (objeto, codigo_en_claro). El código en claro solo existe aquí:
        hay que enviarlo por correo y no se vuelve a poder consultar."""
        cls.objects.filter(usuario=usuario, usado=False, proposito=proposito).update(usado=True)
        codigo = f'{secrets.randbelow(10 ** 6):06d}'
        objeto = cls.objects.create(
            usuario=usuario,
            proposito=proposito,
            codigo_hash=make_password(codigo),
            expira_en=timezone.now() + timedelta(minutes=cls.VIGENCIA_MINUTOS),
        )
        return objeto, codigo

    @classmethod
    def ultimo_vigente(cls, usuario, proposito=Proposito.RECUPERACION):
        """Devuelve el código vigente del usuario para ese propósito, o None si no hay."""
        codigo = cls.objects.filter(
            usuario=usuario, usado=False, proposito=proposito
        ).first()
        return codigo if codigo and codigo.esta_vigente else None

    @property
    def esta_vigente(self):
        return (
            not self.usado
            and self.intentos < self.MAX_INTENTOS
            and timezone.now() < self.expira_en
        )

    def validar(self, codigo):
        """True si el código es correcto y sigue vigente. Si falla, cuenta el intento."""
        if not self.esta_vigente:
            return False
        if check_password(codigo, self.codigo_hash):
            return True
        self.intentos += 1
        self.save(update_fields=['intentos'])
        return False

    def marcar_usado(self):
        self.usado = True
        self.save(update_fields=['usado'])