import re
from django.core.exceptions import ValidationError

class ComplexPasswordValidator:
    def validate(self, password, user=None):
        if len(password) < 8:
            raise ValidationError(
                "La contraseña debe tener al menos 8 caracteres.",
                code='password_too_short',
            )
        if not re.search(r'[A-Z]', password):
            raise ValidationError(
                "La contraseña debe incluir al menos una letra mayúscula.",
                code='password_no_upper',
            )
        if not re.search(r'[a-z]', password):
            raise ValidationError(
                "La contraseña debe incluir al menos una letra minúscula.",
                code='password_no_lower',
            )
        if not re.search(r'\d', password):
            raise ValidationError(
                "La contraseña debe incluir al menos un número.",
                code='password_no_digit',
            )
        if not re.search(r'[^A-Za-z0-9]', password):
            raise ValidationError(
                "La contraseña debe incluir al menos un símbolo (ej. !@#$%).",
                code='password_no_symbol',
            )

    def get_help_text(self):
        return (
            "Tu contraseña debe tener mínimo 8 caracteres, con mayúsculas, "
            "minúsculas, números y símbolos."
        )