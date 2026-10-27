from django import forms

from django.db.models import Q
from django.core.files.uploadedfile import UploadedFile
import re

from .models import Categoria, MovimientoInventario, Producto, Proveedor


class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = [
            'sku', 'nombre', 'categoria', 'proveedor', 'precio', 'precio_oferta',
            'stock', 'imagen', 'descripcion', 'instalacion',
            'especificaciones',  # NUEVO (HU G1-144)
        ]
        labels = {
            'sku': 'Código (SKU)',
            'nombre': 'Título',
            'categoria': 'Categoría',
            'proveedor': 'Proveedor',
            'precio': 'Precio normal',
            'precio_oferta': 'Precio de oferta',
            'stock': 'Existencias disponibles',
            'imagen': 'Imagen',
            'descripcion': 'Descripción Corta',
            'instalacion': 'Uso e Instalación',
            'especificaciones': 'Características Técnicas',  
        }
        
                # G1-147: mensajes de error en español (el proyecto está en en-us)

        
        error_messages = {
            'sku': {
                'required': 'El código (SKU) es obligatorio.',
                'max_length': 'El SKU no puede superar los 30 caracteres.',
                'unique': 'Ya existe un producto con este SKU.',
            },
            'nombre': {
                'required': 'El título del producto es obligatorio.',
                'max_length': 'El título no puede superar los 150 caracteres.',
            },
            'categoria': {
                'required': 'Selecciona una categoría.',
                'invalid_choice': 'Selecciona una categoría válida de la lista.',
            },
            'proveedor': {
                'invalid_choice': 'Selecciona un proveedor válido de la lista.',
            },
            'precio': {
                'required': 'El precio normal es obligatorio.',
                'invalid': 'Ingresa un precio válido (solo números).',
                'max_digits': 'El precio es demasiado grande.',
                'max_whole_digits': 'El precio es demasiado grande.',
                'max_decimal_places': 'El precio solo puede tener 2 decimales.',
            },
            'precio_oferta': {
                'invalid': 'Ingresa un precio de oferta válido (solo números).',
                'max_digits': 'El precio de oferta es demasiado grande.',
                'max_whole_digits': 'El precio de oferta es demasiado grande.',
                'max_decimal_places': 'El precio de oferta solo puede tener 2 decimales.',
            },
            'stock': {
                'required': 'El stock es obligatorio (usa 0 si no hay unidades).',
                'invalid': 'El stock debe ser un número entero.',
                'min_value': 'El stock no puede ser negativo.',
            },
            'imagen': {
                'invalid_image': 'El archivo no es una imagen válida. Usa PNG, JPG o WEBP.',
            },
            'descripcion': {'required': 'La descripción corta es obligatoria.'},
            'instalacion': {'required': 'El campo Uso e Instalación es obligatorio.'},
        }
        widgets = {
            # FileInput simple: evita el "Actualmente / Limpiar" de Django al editar
            'imagen': forms.FileInput(),
            'descripcion': forms.Textarea(attrs={'rows': 2}),
            'instalacion': forms.Textarea(attrs={'rows': 2}),
            # NUEVO: caja de texto más alta, con un ejemplo de cómo llenarla
            'especificaciones': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Potencia: 20W\nVoltaje: 110V\nLúmenes: 1800 lm',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        clase_input = (
            'w-full bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 '
            'rounded-xl px-4 py-3 text-gray-900 dark:text-white focus:outline-none '
            'focus:ring-2 focus:ring-[#F2AE30]'
        )
        for campo in self.fields.values():
            campo.widget.attrs['class'] = clase_input
        # El input de archivo no debe llevar el mismo padding que un texto
        self.fields['imagen'].widget.attrs['class'] = 'hidden'
        self.fields['imagen'].widget.attrs['id'] = 'id_imagen'
        self.fields['imagen'].required = False
        # Selector de proveedor (como en el Figma)
        self.fields['proveedor'].empty_label = 'Sin proveedor'
                # Proveedores activos + el que ya tiene este producto (si se inactivó después),
        # para que al editar no se pierda el vínculo por accidente.
        self.fields['proveedor'].queryset = Proveedor.objects.filter(
            Q(activo=True) | Q(pk=self.instance.proveedor_id)
        )
        
        self.fields['categoria'].empty_label = 'Selecciona una categoría'
                # G1-147: el navegador también avisa antes de enviar (el servidor es la validación real)
        self.fields['precio'].widget.attrs['min'] = '0.01'
        self.fields['precio_oferta'].widget.attrs['min'] = '0.01'

    # ---------- G1-147: validaciones ----------
    def clean_sku(self):
        sku = (self.cleaned_data.get('sku') or '').strip()
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', sku):
            raise forms.ValidationError(
                'El SKU solo puede tener letras, números, punto, guion (-) y guion bajo (_), sin espacios.'
            )
        # Duplicado sin distinguir mayúsculas ("led1" = "LED1"); al editar se ignora a sí mismo
        if Producto.objects.filter(sku__iexact=sku).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Ya existe un producto con este SKU.')
        return sku

    def clean_nombre(self):
        nombre = ' '.join((self.cleaned_data.get('nombre') or '').split())  # quita espacios dobles
        if len(nombre) < 3:
            raise forms.ValidationError('El título debe tener al menos 3 caracteres.')
        if Producto.objects.filter(nombre__iexact=nombre).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Ya existe un producto con este título.')
        return nombre

    def clean_precio(self):
        precio = self.cleaned_data.get('precio')
        if precio is not None and precio <= 0:
            raise forms.ValidationError('El precio debe ser mayor a 0.')
        return precio

    def clean_precio_oferta(self):
        oferta = self.cleaned_data.get('precio_oferta')
        if oferta is not None and oferta <= 0:
            raise forms.ValidationError('El precio de oferta debe ser mayor a 0.')
        return oferta

    def clean_imagen(self):
        imagen = self.cleaned_data.get('imagen')
        # Solo se revisa una imagen NUEVA; si no suben nada, se conserva la anterior
        if isinstance(imagen, UploadedFile):
            if imagen.size > 5 * 1024 * 1024:
                raise forms.ValidationError('La imagen no puede pesar más de 5 MB.')
            formato = getattr(getattr(imagen, 'image', None), 'format', None)
            if formato not in ('JPEG', 'PNG', 'WEBP'):
                raise forms.ValidationError('Formato no permitido. Usa PNG, JPG o WEBP.')
        return imagen


class ProveedorForm(forms.ModelForm):
    # Campo extra (no es de la tabla): casillas para vincular varios productos
    productos = forms.ModelMultipleChoiceField(
        queryset=Producto.objects.filter(activo=True),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Productos que suministra',
    )

    class Meta:
        model = Proveedor
        fields = ['nombre', 'nit', 'contacto', 'telefono', 'correo', 'direccion', 'activo']
        labels = {
            'nombre': 'Nombre de la empresa *',
            'nit': 'NIT *',
            'contacto': 'Persona de contacto',
            'telefono': 'Teléfono',
            'correo': 'Correo electrónico',
            'direccion': 'Dirección',
            'activo': 'Proveedor activo',
        }
        widgets = {
            'nombre': forms.TextInput(attrs={'placeholder': 'Distribuidora Eléctrica S.A.S.'}),
            'nit': forms.TextInput(attrs={'placeholder': '900123456-7'}),
            'contacto': forms.TextInput(attrs={'placeholder': 'Nombre del contacto'}),
            'telefono': forms.TextInput(attrs={'placeholder': '300 000 0000'}),
            'correo': forms.EmailInput(attrs={'placeholder': 'ventas@proveedor.com'}),
            'direccion': forms.TextInput(attrs={'placeholder': 'Calle 10 # 5-20, Sogamoso'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        clase_input = (
            'w-full bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 '
            'rounded-xl px-4 py-3 text-gray-900 dark:text-white focus:outline-none '
            'focus:ring-2 focus:ring-[#F2AE30]'
        )
        for nombre, campo in self.fields.items():
            if nombre not in ('activo', 'productos'):  # checkboxes sin estilo de texto
                campo.widget.attrs['class'] = clase_input
        self.fields['activo'].widget.attrs['class'] = 'w-4 h-4 rounded border-gray-300 text-[#F2AE30] focus:ring-[#F2AE30]'
        
        
        
        
#gv

class ProveedorEditarForm(ProveedorForm):
    """G1-137: edita los datos de contacto. Nombre y NIT no se pueden modificar."""

    class Meta(ProveedorForm.Meta):
        # nombre y nit NO están aquí: el servidor ignora cualquier valor que lleguen en el POST.
        # 'activo' se incluye solo para que el __init__ del padre funcione; se quita abajo
        # (cambiar el estado es otro ticket: G1-138).
        fields = ['contacto', 'telefono', 'correo', 'direccion', 'activo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        del self.fields['activo']

        # Se muestran los productos activos + los que ya tiene este proveedor
        # (así, guardar no desvincula por accidente un producto que se inactivó).
        self.fields['productos'].queryset = Producto.objects.filter(
            Q(activo=True) | Q(proveedor=self.instance)
        ).distinct()
        self.initial['productos'] = list(
            self.instance.productos.values_list('pk', flat=True)
        )

    def clean_telefono(self):
        telefono = self.cleaned_data.get('telefono', '').strip()
        if telefono:
            if not re.fullmatch(r'[\d\s+\-()]+', telefono):
                raise forms.ValidationError(
                    'El teléfono solo puede contener números, espacios, +, - y paréntesis.'
                )
            if not 7 <= len(re.sub(r'\D', '', telefono)) <= 15:
                raise forms.ValidationError('El teléfono debe tener entre 7 y 15 dígitos.')
        return telefono        
    
    


class InactivarProveedorForm(forms.Form):
    """G1-138: valida el motivo obligatorio al inactivar un proveedor."""
    motivo = forms.CharField(
        min_length=5,
        max_length=500,
        error_messages={
            'required': 'Debes indicar el motivo de la inactivación.',
            'min_length': 'El motivo debe tener al menos 5 caracteres.',
            'max_length': 'El motivo no puede superar los 500 caracteres.',
        },
    )


class CategoriaForm(forms.ModelForm):
    """G1-151: crear y editar categorías (un solo campo: el nombre)."""

    class Meta:
        model = Categoria
        fields = ['nombre']
        labels = {'nombre': 'Nombre de la categoría'}
        widgets = {'nombre': forms.TextInput(attrs={'placeholder': 'Ej: Iluminación exterior'})}
        error_messages = {
            'nombre': {
                'required': 'El nombre de la categoría es obligatorio.',
                'max_length': 'El nombre no puede superar los 60 caracteres.',
                'unique': 'Ya existe una categoría con este nombre.',
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nombre'].widget.attrs['class'] = (
            'w-full bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 '
            'rounded-xl px-4 py-3 text-gray-900 dark:text-white focus:outline-none '
            'focus:ring-2 focus:ring-[#F2AE30]'
        )

    def clean_nombre(self):
        nombre = ' '.join((self.cleaned_data.get('nombre') or '').split())  # quita espacios dobles
        if len(nombre) < 2:
            raise forms.ValidationError('El nombre debe tener al menos 2 caracteres.')
        # Duplicado sin distinguir mayúsculas ni tildes de mayúscula (se compara en Python
        # porque SQLite no ignora mayúsculas en letras con tilde). Al editar se ignora a sí misma.
        otros = Categoria.objects.exclude(pk=self.instance.pk).values_list('nombre', flat=True)
        if any(otro.casefold() == nombre.casefold() for otro in otros):
            raise forms.ValidationError('Ya existe una categoría con este nombre.')
        return nombre


class EntradaInventarioForm(forms.Form):
    """G1-149: registrar la llegada de mercancía (producto + cantidad)."""
    MAX_CANTIDAD = 100000

    producto = forms.ModelChoiceField(
        queryset=Producto.objects.none(),
        label='Producto',
        empty_label='Selecciona un producto',
        error_messages={
            'required': 'Selecciona el producto que ingresó.',
            'invalid_choice': 'Selecciona un producto válido de la lista.',
        },
    )
    cantidad = forms.IntegerField(
        label='Cantidad recibida',
        min_value=1,
        max_value=MAX_CANTIDAD,
        error_messages={
            'required': 'Indica la cantidad recibida.',
            'invalid': 'La cantidad debe ser un número entero.',
            'min_value': 'La cantidad debe ser mayor a 0.',
            'max_value': f'La cantidad no puede superar {MAX_CANTIDAD:,} unidades por entrada.'.replace(',', '.'),
        },
    )
    observacion = forms.CharField(
        label='Observación (opcional)',
        max_length=200,
        required=False,
        error_messages={'max_length': 'La observación no puede superar los 200 caracteres.'},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo productos activos: un producto inactivo está retirado de la operación (G1-146)
        self.fields['producto'].queryset = Producto.objects.filter(activo=True).order_by('nombre')
        self.fields['producto'].label_from_instance = lambda p: f'{p.nombre} (SKU {p.sku}) · stock actual: {p.stock}'
        clase_input = (
            'w-full bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 '
            'rounded-xl px-4 py-3 text-gray-900 dark:text-white focus:outline-none '
            'focus:ring-2 focus:ring-[#F2AE30]'
        )
        for campo in self.fields.values():
            campo.widget.attrs['class'] = clase_input
        self.fields['cantidad'].widget.attrs.update({'min': '1', 'max': str(self.MAX_CANTIDAD), 'placeholder': 'Ej: 25'})
        self.fields['observacion'].widget.attrs['placeholder'] = 'Ej: Factura 1234 del proveedor'

    def clean_observacion(self):
        return ' '.join((self.cleaned_data.get('observacion') or '').split())