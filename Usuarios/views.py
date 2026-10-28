from django.views.decorators.http import require_POST
from django.conf import settings
from django.core.mail import send_mail
from .models import CodigoRecuperacion, CodigoDobleFactor
from .forms import SolicitarRecuperacionForm

from django.contrib import messages
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.core.paginator import Paginator

from .models import Usuario
from .forms import CrearUsuarioInternoForm, EditarRolForm
from django.shortcuts import get_object_or_404
from productos.models import Producto  # NUEVO: para mostrar productos en el inicio


def inicio(request):
    # NUEVO: productos que el administrador marcó como "Destacado en Inicio" (máximo 4)
    productos_destacados = Producto.objects.filter(
        activo=True, destacado_en_inicio=True
    )[:4]
    return render(request, 'inicio.html', {
        'productos_destacados': productos_destacados,
    })


def login_view(request):
    if request.user.is_authenticated:
        return redirect('inicio')

    error = None
    if request.method == 'POST':
        correo = (request.POST.get('correo') or '').strip().lower()
        contrasena = request.POST.get('contrasena')

        # Buscamos al usuario ANTES de autenticar: si la cuenta está bloqueada,
        # authenticate() devuelve None aunque la clave sea correcta.
        usuario = Usuario.objects.filter(email=correo).first()

        if usuario and usuario.estado_cuenta == Usuario.EstadoCuenta.BLOQUEADA:
            error = "Tu cuenta está bloqueada por intentos fallidos. Contacta al administrador."
        elif usuario and usuario.estado_cuenta == Usuario.EstadoCuenta.SUSPENDIDA:
            error = "Tu cuenta está suspendida. Contacta al administrador."
        else:
            user = authenticate(request, username=correo, password=contrasena)
            if user is not None and user.doble_factor_activo:
                # G1-127: la contraseña es correcta, pero falta el segundo factor
                _enviar_codigo_doble_factor(user)
                request.session['doble_factor_usuario_id'] = user.pk
                return redirect('verificar_doble_factor')
            if user is not None:
                # Login correcto: se reinicia el contador de intentos
                if user.intentos_fallidos:
                    user.intentos_fallidos = 0
                    user.save()
                login(request, user)
                return redirect('inicio')

            error = "Credenciales incorrectas"
            if usuario:
                usuario.intentos_fallidos += 1
                if usuario.intentos_fallidos >= Usuario.MAX_INTENTOS:
                    usuario.estado_cuenta = Usuario.EstadoCuenta.BLOQUEADA
                    error = "Tu cuenta fue bloqueada por 3 intentos fallidos. Contacta al administrador."
                usuario.save()

    return render(request, 'login.html', {'error': error})


def logout_view(request):
    logout(request)
    return redirect('login')


def _enviar_codigo_doble_factor(usuario):
    _, codigo = CodigoDobleFactor.generar(usuario)
    send_mail(
        subject='Código de acceso - TECNILED',
        message=(
            f'Hola {usuario.first_name or usuario.email},\n\n'
            f'Tu código de acceso es: {codigo}\n'
            f'Es válido por {CodigoDobleFactor.VIGENCIA_MINUTOS} minutos y solo se puede usar una vez.\n\n'
            'Si no intentaste iniciar sesión, cambia tu contraseña.'
        ),
        from_email=None,
        recipient_list=[usuario.email],
    )


def verificar_doble_factor(request):
    if request.user.is_authenticated:
        return redirect('inicio')

    usuario_id = request.session.get('doble_factor_usuario_id')
    usuario = Usuario.objects.filter(
        pk=usuario_id, estado_cuenta=Usuario.EstadoCuenta.ACTIVA
    ).first() if usuario_id else None
    if usuario is None:
        request.session.pop('doble_factor_usuario_id', None)
        return redirect('login')

    error = None
    if request.method == 'POST':
        codigo = (request.POST.get('codigo') or '').strip()
        objeto = CodigoDobleFactor.ultimo_vigente(usuario)
        if objeto and len(codigo) == 6 and codigo.isdigit() and objeto.validar(codigo):
            objeto.marcar_usado()
            request.session.pop('doble_factor_usuario_id', None)
            usuario.intentos_fallidos = 0
            usuario.save()
            login(request, usuario, backend='Usuarios.backends.EmailBackend')
            return redirect('inicio')
        error = 'El código es incorrecto o venció. Revisa tu correo o pide uno nuevo.'

    return render(request, 'verificar_doble_factor.html', {'error': error, 'correo': usuario.email})


@require_POST
def reenviar_doble_factor(request):
    usuario_id = request.session.get('doble_factor_usuario_id')
    usuario = Usuario.objects.filter(pk=usuario_id).first() if usuario_id else None
    if usuario is None:
        return redirect('login')
    _enviar_codigo_doble_factor(usuario)
    messages.info(request, 'Te enviamos un nuevo código.')
    return redirect('verificar_doble_factor')


@login_required
def seguridad_cuenta(request):
    if request.method == 'POST':
        activar = request.POST.get('accion') == 'activar'
        request.user.doble_factor_activo = activar
        request.user.save(update_fields=['doble_factor_activo'])
        if activar:
            messages.success(request, 'Verificación en dos pasos activada.')
        else:
            messages.info(request, 'Verificación en dos pasos desactivada.')
        return redirect('seguridad_cuenta')
    return render(request, 'seguridad_cuenta.html')


@login_required
@permission_required('Usuarios.gestionar_usuarios', raise_exception=True)
def usuarios_lista(request):
    query = request.GET.get('q', '').strip()

    usuarios = Usuario.objects.all().order_by('first_name', 'last_name')
    if query:
        usuarios = usuarios.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
            | Q(documento__icontains=query)
        )

    paginador = Paginator(usuarios, 10)
    pagina = paginador.get_page(request.GET.get('page'))

    return render(request, 'usuarios_lista.html', {
        'usuarios': pagina,
        'query': query,
    })

@login_required
@permission_required('Usuarios.gestionar_usuarios', raise_exception=True)
def crear_usuario(request):
    if request.method == 'POST':
        form = CrearUsuarioInternoForm(request.POST)
        if form.is_valid():
            usuario = form.save()
            messages.success(request, f'Cuenta creada para {usuario.email}.')
            return redirect('usuarios_lista')
    else:
        form = CrearUsuarioInternoForm()

    return render(request, 'usuarios_crear.html', {'form': form})


@login_required
@permission_required('Usuarios.gestionar_usuarios', raise_exception=True)
def editar_rol(request, usuario_id):
    usuario = get_object_or_404(Usuario, pk=usuario_id)

    if request.method == 'POST':
        form = EditarRolForm(request.POST, instance=usuario)
        if form.is_valid():
            es_propia = usuario == request.user
            correo_enviado = (request.POST.get('email') or usuario.email).strip().lower()
            if correo_enviado != usuario.email:
                form.add_error('email', 'El correo no se puede modificar.')
            elif es_propia and form.cleaned_data['rol'] != Usuario.Rol.ADMINISTRADOR:
                form.add_error('rol', 'No puedes quitarte tu propio rol de administrador.')
            elif es_propia and form.cleaned_data['estado_cuenta'] != Usuario.EstadoCuenta.ACTIVA:
                form.add_error('estado_cuenta', 'No puedes suspender ni bloquear tu propia cuenta.')
            else:
                form.save()
                messages.success(request, f'Cuenta de {usuario.email} actualizada.')
                return redirect('usuarios_lista')
    else:
        form = EditarRolForm(instance=usuario)

    return render(request, 'usuarios_editar_rol.html', {'form': form, 'usuario': usuario})

def recuperar_contrasena(request):
    if request.user.is_authenticated:
        return redirect('inicio')

    if request.method == 'POST':
        form = SolicitarRecuperacionForm(request.POST)
        if form.is_valid():
            correo = form.cleaned_data['correo'].strip().lower()
            usuario = Usuario.objects.filter(email=correo).first()
            # Solo cuentas activas reciben código (las bloqueadas no se saltan el bloqueo)
            if usuario and usuario.estado_cuenta == Usuario.EstadoCuenta.ACTIVA:
                _, codigo = CodigoRecuperacion.generar(usuario)
                send_mail(
                    subject='Código de recuperación - TECNILED',
                    message=(
                        f'Hola {usuario.first_name or usuario.email},\n\n'
                        f'Tu código de recuperación es: {codigo}\n'
                        f'Es válido por {CodigoRecuperacion.VIGENCIA_MINUTOS} minutos y solo se puede usar una vez.\n\n'
                        'Si no lo solicitaste, ignora este mensaje.'
                    ),
                    from_email=None,
                    recipient_list=[usuario.email],
                )
            # Mismo mensaje exista o no el correo (no revela qué cuentas existen)
            request.session['recuperacion_correo'] = correo
            messages.info(request, 'Si el correo está registrado, te enviamos un código de recuperación.')
            return redirect('login')  # provisional: en el PASO 3 irá a la pantalla del código
    else:
        form = SolicitarRecuperacionForm()

    return render(request, 'recuperar_contrasena.html', {'form': form})

@login_required
@permission_required('Usuarios.gestionar_usuarios', raise_exception=True)
def usuario_detalle(request, usuario_id):
    usuario = get_object_or_404(Usuario, pk=usuario_id)
    # CORREGIDO: el archivo se llama usuarios_detalle.html (con "s")
    return render(request, 'usuarios_detalle.html', {'usuario': usuario})

@login_required
@permission_required('Usuarios.gestionar_usuarios', raise_exception=True)
@require_POST
def inactivar_usuario(request, usuario_id):
    usuario = get_object_or_404(Usuario, pk=usuario_id)

    if usuario == request.user:
        messages.error(request, 'No puedes inactivar tu propia cuenta.')
    elif usuario.estado_cuenta != Usuario.EstadoCuenta.ACTIVA:
        # Criterio 2: ya está inactivo, se impide la acción
        messages.warning(
            request,
            f'La cuenta de {usuario.email} ya no está activa (estado: {usuario.get_estado_cuenta_display()}).'
        )
    else:
        usuario.estado_cuenta = Usuario.EstadoCuenta.SUSPENDIDA
        usuario.save()
        messages.success(request, f'La cuenta de {usuario.email} fue inactivada.')

    return redirect('usuario_detalle', usuario_id=usuario.id)