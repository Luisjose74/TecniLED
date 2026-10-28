from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory

from productos.models import Producto, Proveedor

from .models import DetalleOrdenCompra, OrdenCompra

# Mismas clases de Tailwind que usan los formularios de productos
CLASE_INPUT = (
    'w-full bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 '
    'rounded-xl px-4 py-3 text-gray-900 dark:text-white focus:outline-none '
    'focus:ring-2 focus:ring-[#F2AE30]'
)


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
        # G1-132: solo proveedores activos (mismo criterio que ya usa ProductoForm)
        self.fields['proveedor'].queryset = Proveedor.objects.filter(activo=True)
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
        self.fields['producto'].empty_label = 'Selecciona un producto'


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
            productos.append(form.cleaned_data['producto'])
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