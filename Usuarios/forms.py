from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import Usuario


class CrearUsuarioInternoForm(forms.ModelForm):
    apellido = forms.CharField(label='Apellido', required=False, max_length=150)
    contrasena = forms.CharField(label='Contraseña', widget=forms.PasswordInput, required=True)

    class Meta:
        model = Usuario
        fields = ['first_name', 'apellido', 'email', 'documento', 'telefono', 'rol']
        labels = {'first_name': 'Nombre'}

    def clean_contrasena(self):
        contrasena = self.cleaned_data['contrasena']
        validate_password(contrasena)
        return contrasena

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        clase_input = 'w-full px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-[#F2AE30] outline-none'
        for campo in self.fields.values():
            campo.widget.attrs['class'] = clase_input
        # NUEVO: espacio a la derecha del campo contraseña para el botón del ojo
        self.fields['contrasena'].widget.attrs['class'] = clase_input + ' pr-10'

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
        fields = ['first_name', 'last_name', 'email', 'documento', 'telefono', 'rol', 'estado_cuenta']
        labels = {
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'documento': 'Cédula',
            'telefono': 'Teléfono',
            'estado_cuenta': 'Estado de la cuenta',
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