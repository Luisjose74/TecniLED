# AGENTS.md

Django 6.1 monolith for TECNILED (lighting store + internal admin panel). UI text is Spanish (`LANGUAGE_CODE = es-co`). Tailwind is loaded from a CDN — there is **no** package.json, bundler, linter, formatter, typechecker, or CI workflow.

## Commands

Use the local virtualenv on Windows:

```powershell
venv\Scripts\python.exe manage.py migrate          # db.sqlite3 is gitignored; a clone has no DB
venv\Scripts\python.exe manage.py runserver
venv\Scripts\python.exe manage.py test             # full suite ~5 min (~260 tests)
venv\Scripts\python.exe manage.py test Usuarios.tests.ContrasteTests   # focused run
venv\Scripts\python.exe manage.py test productos   # one app
venv\Scripts\python.exe manage.py makemigrations --check --dry-run     # currently: no changes
venv\Scripts\python.exe manage.py loaddata preguntas_iniciales         # seeds /ayuda/ FAQ; not automatic
```

- Tests use their own SQLite DB. Only `productos` image tests touch media, via a temporary `MEDIA_ROOT`.
- `db.sqlite3`, `media/`, and `backups/` are local only and must never be committed.

## Layout

- Apps: `Usuarios` (auth, roles, 2FA), `productos` (catalog, suppliers, categories, inventory entries), `compras`, `reportes`, `sistema` (SQLite backups), `ayuda` (FAQ), `notificaciones`.
- `TECNILED/settings.py` is the only settings module: `DEBUG = True`, SQLite, console email backend, hardcoded `SECRET_KEY`. No `.env`/env-var handling.
- `TECNILED/urls.py` mounts most apps at the site root (`/productos/`, `/usuarios/`); only `sistema/`, `ayuda/`, `notificaciones/` use prefixes.

## Templates

Two template conventions coexist:

- `template/` — shared: `base.html` (storefront), `admin_base.html` (panel), `partials/`.
- `Usuarios/template/` — singular name, added to `TEMPLATES['DIRS']`, so its pages are referenced by bare name (`'usuarios_lista.html'`).
- All other apps: `app/templates/app/*.html` and referenced as `'productos/productos_lista.html'`.

Rules enforced by tests:

- Panel pages extend `admin_base.html`; public pages extend `base.html` (`PlantillasBaseTests` asserts a panel page does not render `base.html`).
- Panel pages fill `{% block title %}`, `titulo_seccion`, `migas_actual` (optionally `migas_intermedias`).
- `IconosConDescripcionTests` / `ContrasteTests` scan **every** `*.html` under `BASE_DIR` (only `venv` is skipped). So any mockup or scratch HTML is scanned too: every `<svg>` needs `aria-hidden="true"`, icon-only `<button>`/`<a>` need both `title` and `aria-label`, and never combine `text-white` with `bg-[#F2AE30]` or `bg-red-500`.

UI styling is governed by `docs/guia_estilo.md`: primary `#F2AE30` with **black** text, danger `bg-red-600`, a `dark:` variant for every color, Spanish sentence-case copy. Reusable CSS variables/classes (`btn-principal`, `btn-secundario`, `btn-peligro`) live in `static/css/style.css`. Use `partials/mensajes.html`, `partials/modal_confirmacion.html` (+ `data-confirmar` on the form), and `partials/miga.html` rather than rewriting them.

## Auth and permissions

- Custom user `Usuarios.Usuario` (`AUTH_USER_MODEL`); login is by email, and `Usuario.save()` forces `username = email`.
- Roles: `administrador`, `control_inventario`, `cliente`. Permission codenames: `Usuarios.gestionar_usuarios`, `Usuarios.gestionar_inventario`, `Usuarios.gestionar_compras`, plus `sistema.gestionar_respaldos`.
- `Usuarios/apps.py` seeds role groups on `post_migrate` **only when the group is newly created**, and `Usuario.save()` re-syncs the user into the group for its `rol`. Adding a permission means updating `Meta.permissions` and `PERMISOS_POR_ROL` in `Usuarios/models.py`, migrating, then granting it explicitly (or deleting/recreating the group) — existing groups are not updated by `post_migrate`.
- Guard views with `@login_required` + `@permission_required('...', raise_exception=True)`. Denials go to `notificaciones.views.error_403`, which records a notification and renders `403.html`; tests expect HTTP 403, not a redirect.
- Every login needs a 6-digit email code (2FA) unless the browser has a trusted-device cookie. Email is console-only, so the code appears in the `runserver` terminal. To smoke-test panel pages without 2FA, log in at `/admin/` with a staff user, then navigate to the app URLs.

## Gotchas

- Password policy is 8+ chars with uppercase, lowercase, digit, and symbol; test passwords look like `Prueba123!`.
- Do not "fix" the title-case `verbose_name`s in `productos/models.py` (e.g. "Precio Normal"): `docs/revision_ortografia.md` records that they were deliberately left without a migration.
- `manage.py restaurar_bd <ruta> --si` restores only backups registered in `RegistroRespaldo`, validates gzip + `PRAGMA integrity_check`, and creates a safety backup first. Restoring swaps the whole SQLite file.
- Use timezone-aware datetimes (`USE_TZ = True`, `America/Bogota`).

## Git conventions

Work lands via PRs into `main` (`staging` also exists). Branch names follow `epica/...`, `historia/G1-<id>-...`, `fix/...`, and commit messages include the Jira ID, e.g. `G1-127: ...`.
