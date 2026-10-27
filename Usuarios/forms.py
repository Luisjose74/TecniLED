from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import Usuario


class CrearUsuarioInternoForm(forms.ModelForm):
    apellido = forms.CharField(label='Apellido', required=False, max_length=150)
    contrasena = forms.CharField(
        label='Contraseña',
        required=True,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    contrasena2 = forms.CharField(
        label='Confirmar contraseña',
        required=True,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )

    class Meta:
        model = Usuario
        fields = [
            'first_name', 'apellido', 'email', 'tipo_documento',
            'documento', 'telefono', 'rol',
        ]
        labels = {'first_name': 'Nombre'}
        widgets = {
            # Cada campo declara qué es, para que el gestor de contraseñas no
            # confunda el teléfono con el nombre de usuario del formulario
            'email': forms.EmailInput(attrs={'autocomplete': 'email'}),
            'documento': forms.TextInput(attrs={
                'autocomplete': 'off', 'inputmode': 'numeric',
            }),
            'telefono': forms.TextInput(attrs={
                'type': 'tel', 'autocomplete': 'tel', 'inputmode': 'tel',
            }),
        }

    def clean_contrasena(self):
        contrasena = self.cleaned_data['contrasena']
        validate_password(contrasena)
        return contrasena

    def clean(self):
        datos = super().clean()
        contrasena = datos.get('contrasena')
        confirmacion = datos.get('contrasena2')
        if contrasena and confirmacion and contrasena != confirmacion:
            self.add_error('contrasena2', 'Las contraseñas no coinciden.')
        return datos

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        clase_input = 'w-full px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-[#F2AE30] outline-none'
        for campo in self.fields.values():
            campo.widget.attrs['class'] = clase_input
        # El tipo de documento arranca en Cédula de Ciudadanía, el más común.
        self.fields['tipo_documento'].initial = Usuario.TipoDocumento.CC
        self.fields['tipo_documento'].required = False
        # Espacio a la derecha de las contraseñas para el botón del ojo
        for nombre in ('contrasena', 'contrasena2'):
            self.fields[nombre].widget.attrs['class'] = clase_input + ' pr-10'
        # La lista visual de requisitos describe el campo para lectores de pantalla
        self.fields['contrasena'].widget.attrs['aria-describedby'] = 'requisitos-contrasena'

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.last_name = self.cleaned_data.get('apellido', '')
        usuario.set_password(self.cleaned_data['contrasena'])
        if commit:
            usuario.save()
        return usuario


class EditarRolForm(forms.ModelForm):
    # Campo no permitido: se muestra pero Django ignora lo que llegue por POST
    email = forms.EmailField(label='Correo electrónico', required=False, disabled=True)

    class Meta:
        model = Usuario
        fields = [
            'first_name', 'last_name', 'email', 'tipo_documento',
            'documento', 'telefono', 'rol', 'estado_cuenta',
        ]
        labels = {
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'documento': 'Número de documento',
            'telefono': 'Teléfono',
            'estado_cuenta': 'Estado de la cuenta',
        }
        widgets = {
            'documento': forms.TextInput(attrs={
                'autocomplete': 'off', 'inputmode': 'numeric',
            }),
            'telefono': forms.TextInput(attrs={
                'type': 'tel', 'autocomplete': 'tel', 'inputmode': 'tel',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        clase_input = 'w-full px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-[#F2AE30] outline-none'
        for campo in self.fields.values():
            campo.widget.attrs['class'] = clase_input
        self.fields['email'].widget.attrs['class'] = clase_input + ' opacity-60 cursor-not-allowed'
            
class SolicitarRecuperacionForm(forms.Form):
    correo = forms.EmailField(label='Correo electrónico')
    
class SolicitarRecuperacionForm(forms.Form):
    correo = forms.EmailField(label='Correo electrónico')


class VerificarCodigoForm(forms.Form):
    """Código de 6 dígitos del doble factor (G1-303)."""
    codigo = forms.CharField(label='Código de verificación', min_length=6, max_length=6)

    def clean_codigo(self):
        codigo = self.cleaned_data['codigo'].strip()
        if not codigo.isdigit():
            raise forms.ValidationError('El código debe tener solo números.')
        return codigo