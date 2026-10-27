from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction


class Proveedor(models.Model):
    nombre = models.CharField(max_length=150)
    nit = models.CharField('NIT', max_length=20, unique=True)
    telefono = models.CharField(max_length=20, blank=True)
    correo = models.EmailField(blank=True)
    contacto = models.CharField('Persona de contacto', max_length=100, blank=True)
    direccion = models.CharField('Dirección', max_length=200, blank=True)
    activo = models.BooleanField(default=True)
    motivo_inactivacion = models.TextField('Motivo de inactivación', blank=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'proveedores'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre
    
    
    def inactivar(self, motivo):
        """G1-138: pasa a inactivo guardando el motivo. No borra nada del proveedor."""
        if not self.activo:
            raise ValueError('El proveedor ya está inactivo.')
        self.activo = False
        self.motivo_inactivacion = motivo
        # fecha_actualizacion debe ir en update_fields para que auto_now la actualice
        self.save(update_fields=['activo', 'motivo_inactivacion', 'fecha_actualizacion'])
        

    def reactivar(self):
        """Vuelve a activar un proveedor inactivo y limpia el motivo anterior."""
        if self.activo:
            raise ValueError('El proveedor ya está activo.')
        self.activo = True
        self.motivo_inactivacion = ''
        self.save(update_fields=['activo', 'motivo_inactivacion', 'fecha_actualizacion'])


class Categoria(models.Model):
    """G1-151: categorías para clasificar productos (se crean y editan desde el panel)."""
    nombre = models.CharField('Nombre', max_length=60, unique=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Categoría'
        verbose_name_plural = 'Categorías'

    def __str__(self):
        return self.nombre
    


class Producto(models.Model):

    # --- Identificación ---
    sku = models.CharField(
        'Código (SKU)', max_length=30, unique=True,
        help_text='Código único del producto. Se usa para buscarlo rápidamente.',
    )
    nombre = models.CharField('Título', max_length=150)

    # --- Clasificación y precio (campos del formulario del diseño) ---
        # PROTECT: no se puede borrar una categoría que todavía tiene productos
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name='productos')
    proveedor = models.ForeignKey(
        Proveedor, on_delete=models.PROTECT,
        null=True, blank=True, related_name='productos',
    )
    precio = models.DecimalField('Precio Normal', max_digits=10, decimal_places=2)
    precio_oferta = models.DecimalField(
        'Precio de Oferta', max_digits=10, decimal_places=2, null=True, blank=True
    )
    stock = models.PositiveIntegerField('Stock Disponible', default=0)

    # --- Imagen ---
    imagen = models.ImageField('Imagen', upload_to='productos/', blank=True, null=True)

    # --- Contenido ---
    descripcion = models.TextField('Descripción Corta')
    instalacion = models.TextField('Uso e Instalación')

    especificaciones = models.TextField(
        'Características Técnicas', blank=True,
        help_text='Una característica por línea. Ejemplo: Potencia: 20W',
    )

    # --- Estado / catálogo ---
    activo = models.BooleanField('Activo', default=True)
    destacado_en_inicio = models.BooleanField('Destacado en Inicio', default=False)

    # --- Auditoría ---
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nombre']
        permissions = []  # No creamos permisos nuevos: reusamos 'Usuarios.gestionar_inventario'

    def __str__(self):
        return f'{self.sku} - {self.nombre}'

    def get_categoria_display(self):
        """Compatibilidad: inicio.html, producto_detalle.html y la lista siguen usando este nombre."""
        return self.categoria.nombre

    def porcentaje_descuento(self):
        """Devuelve el % de descuento (ej: 23) o 0 si no tiene oferta."""
        if self.precio_oferta and self.precio:
            descuento = (self.precio - self.precio_oferta) / self.precio * 100
            return round(descuento)
        return 0

    def lista_especificaciones(self):
        """Convierte el texto de especificaciones en una lista de (nombre, valor)."""
        lista = []
        for linea in self.especificaciones.splitlines():
            linea = linea.strip()
            if linea == '':
                continue
            if ':' in linea:
                nombre, valor = linea.split(':', 1)
                lista.append((nombre.strip(), valor.strip()))
            else:
                lista.append(('', linea))
        return lista

    def clean(self):
        # Regla de negocio: si hay precio de oferta, debe ser menor al precio normal
        if self.precio_oferta and self.precio and self.precio_oferta >= self.precio:
            raise ValidationError({
                'precio_oferta': 'El precio de oferta debe ser menor al precio normal.'
            })

        


class MovimientoInventario(models.Model):
    """G1-149: historial de movimientos de stock. Cada entrada de mercancía deja un registro."""

    class Tipo(models.TextChoices):
        ENTRADA = 'entrada', 'Entrada'
        SALIDA = 'salida', 'Salida'  # reservado: lo usarán otras historias (p. ej. anular una orden de compra)

    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='movimientos')
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.ENTRADA)
    cantidad = models.PositiveIntegerField()  # siempre positiva; el tipo indica si suma o resta
    stock_resultante = models.PositiveIntegerField()  # stock del producto justo después del movimiento
    observacion = models.CharField('Observación', max_length=200, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='movimientos_inventario',
    )
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-fecha', '-id']
        verbose_name = 'Movimiento de inventario'
        verbose_name_plural = 'Movimientos de inventario'

    def __str__(self):
        signo = '+' if self.tipo == self.Tipo.ENTRADA else '-'
        return f'{self.producto} {signo}{self.cantidad}'

    @classmethod
    def registrar_entrada(cls, producto, cantidad, usuario=None, observacion=''):
        """Suma `cantidad` al stock del producto y guarda el movimiento, todo en una sola transacción."""
        if cantidad is None or cantidad < 1:
            raise ValueError('La cantidad debe ser mayor a 0.')
        with transaction.atomic():
            # Se vuelve a leer el producto bloqueándolo, para no pisar otra entrada simultánea
            producto = Producto.objects.select_for_update().get(pk=producto.pk)
            if not producto.activo:
                raise ValueError('No se puede registrar entrada en un producto inactivo.')
            producto.stock += cantidad
            producto.save(update_fields=['stock', 'actualizado_en'])
            return cls.objects.create(
                producto=producto, tipo=cls.Tipo.ENTRADA, cantidad=cantidad,
                stock_resultante=producto.stock, usuario=usuario, observacion=observacion,
            )