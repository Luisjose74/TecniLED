from pathlib import Path

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.forms import BaseInlineFormSet, inlineformset_factory

from productos.models import Producto, Proveedor

from .models import DetalleOrdenCompra, OrdenCompra

# Mismas clases de Tailwind que usan los formularios de productos
CLASE_INPUT = (
    'w-full bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 '
    'rounded-xl px-4 py-3 text-gray-900 dark:text-white focus:outline-none '
    'focus:ring-2 focus:ring-[#F2AE30]'
)

# G1-159: firma real del archivo, para no aceptar un .pdf que no sea PDF
FIRMAS_REMISION = {
    '.pdf': (b'%PDF-',),
    '.png': (b'\x89PNG\r\n\x1a\n',),
    '.jpg': (b'\xff\xd8\xff',),
    '.jpeg': (b'\xff\xd8\xff',),
}


def firma_remision_valida(archivo):
    """Comprueba que el contenido del archivo coincida con su extensión."""
    extension = Path(archivo.name).suffix.lower()
    firmas = FIRMAS_REMISION.get(extension)
    if not firmas:
        return False
    inicio = archivo.read(8)
    archivo.seek(0)
    return any(inicio.startswith(firma) for firma in firmas)


class OrdenCompraForm(forms.ModelForm):
    """Cabecera de la orden: número, fecha y proveedor (G1-158 y G1-132)."""

    class Meta:
        model = OrdenCompra
        fields = ['numero_factura', 'fecha', 'proveedor']
        widgets = {
            'numero_factura': forms.TextInput(attrs={'placeholder': 'F-0001'}),
            'fecha': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }
        error_messages = {
            'numero_factura': {
                'required': 'Debes indicar el número de orden o factura.',
                'unique': 'Ya existe una orden de compra con ese número.',
            },
            'fecha': {
                'required': 'Debes indicar la fecha.',
                'invalid': 'Escribe una fecha válida.',
            },
            'proveedor': {
                'required': 'Debes seleccionar un proveedor.',
                'invalid_choice': 'Selecciona un proveedor activo de la lista.',
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs['class'] = CLASE_INPUT
        # G1-132: solo proveedores activos (mismo criterio que ya usa ProductoForm).
        # G1-164: al editar se conserva el proveedor actual aunque esté inactivo.
        proveedores = Proveedor.objects.filter(activo=True)
        if self.instance and self.instance.pk and self.instance.proveedor_id:
            proveedores = Proveedor.objects.filter(
                Q(activo=True) | Q(pk=self.instance.proveedor_id)
            )
        self.fields['proveedor'].queryset = proveedores
        self.fields['proveedor'].empty_label = 'Selecciona un proveedor'


class DetalleOrdenCompraForm(forms.ModelForm):
    """Una línea de la orden: producto, cantidad y precio unitario."""

    class Meta:
        model = DetalleOrdenCompra
        fields = ['producto', 'cantidad', 'precio_unitario']
        widgets = {
            'cantidad': forms.NumberInput(attrs={'min': 1, 'placeholder': 'Cant.'}),
            'precio_unitario': forms.NumberInput(
                attrs={'min': '0.01', 'step': '0.01', 'placeholder': 'Precio'}
            ),
        }
        error_messages = {
            'producto': {'required': 'Selecciona un producto.'},
            'cantidad': {
                'required': 'Indica la cantidad.',
                'invalid': 'La cantidad debe ser un número entero.',
            },
            'precio_unitario': {
                'required': 'Indica el precio.',
                'invalid': 'Escribe un precio válido.',
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs['class'] = CLASE_INPUT
        # Accesibilidad: cada línea de la orden se anuncia con su nombre
        etiquetas = {
            'producto': 'Producto',
            'cantidad': 'Cantidad',
            'precio_unitario': 'Precio unitario',
        }
        for nombre, etiqueta in etiquetas.items():
            self.fields[nombre].widget.attrs['aria-label'] = etiqueta
        self.fields['producto'].queryset = Producto.objects.filter(activo=True)
        # G1-164: al editar se conserva el producto de la línea aunque esté inactivo
        if self.instance and self.instance.pk and self.instance.producto_id:
            self.fields['producto'].queryset = Producto.objects.filter(
                Q(activo=True) | Q(pk=self.instance.producto_id)
            )
        self.fields['producto'].empty_label = 'Selecciona un producto'
        # G1-164: en el formulario de edición cada línea se puede marcar para borrar
        if 'DELETE' in self.fields:
            self.fields['DELETE'].widget.attrs.update({
                'class': 'w-4 h-4 rounded border-gray-300 text-red-600 focus:ring-red-500',
                'aria-label': 'Eliminar esta línea',
                'title': 'Eliminar esta línea',
            })


class BaseDetalleFormSet(BaseInlineFormSet):
    """Reglas que afectan a TODAS las líneas juntas."""

    def clean(self):
        super().clean()
        if any(self.errors):
            return  # primero se corrigen los errores de cada línea
        productos = []
        for form in self.forms:
            if not form.cleaned_data:
                continue  # línea vacía: se ignora
            if form.cleaned_data.get('DELETE'):
                continue  # G1-164: línea marcada para eliminar
            producto = form.cleaned_data.get('producto')
            if producto is None:
                continue
            productos.append(producto)
        if not productos:
            raise ValidationError('Debes agregar al menos un producto a la orden.')
        if len(productos) != len(set(productos)):
            raise ValidationError(
                'Hay un producto repetido. Suma las cantidades en una sola línea.'
            )


DetalleFormSet = inlineformset_factory(
    OrdenCompra,
    DetalleOrdenCompra,
    form=DetalleOrdenCompraForm,
    formset=BaseDetalleFormSet,
    extra=1,
    can_delete=False,
)

# G1-164: al editar una orden pendiente se pueden quitar líneas existentes
DetalleEdicionFormSet = inlineformset_factory(
    OrdenCompra,
    DetalleOrdenCompra,
    form=DetalleOrdenCompraForm,
    formset=BaseDetalleFormSet,
    extra=1,
    can_delete=True,
)


class RemisionForm(forms.ModelForm):
    """G1-159: adjunta la remisión o factura del proveedor a una orden."""

    class Meta:
        model = OrdenCompra
        fields = ['remision']
        widgets = {
            'remision': forms.ClearableFileInput(
                attrs={'accept': '.pdf,.png,.jpg,.jpeg'}
            ),
        }
        error_messages = {
            'remision': {
                'required': 'Debes seleccionar el archivo de la remisión o factura.',
                'invalid': 'No se pudo leer el archivo. Intenta de nuevo.',
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['remision'].required = True
        self.fields['remision'].widget.attrs.update({
            'class': CLASE_INPUT,
            'aria-describedby': 'ayuda-remision',
        })

    def clean_remision(self):
        archivo = self.cleaned_data.get('remision')
        if not archivo:
            return archivo
        if not firma_remision_valida(archivo):
            raise ValidationError(
                'El archivo no es un PDF o una imagen JPG/PNG válida.'
            )
        return archivo
