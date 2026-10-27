# Revisión de ortografía, idioma y mayúsculas

> Historia de Jira: G1-1198 — Calidad: revisión de ortografía, idioma y uso de mayúsculas.
> Ítems 3 y 11 de la lista de chequeo del prototipo.

## Alcance

Se revisó el texto visible de las 23 plantillas del proyecto (`template/`, `Usuarios/template/`,
`productos/templates/`, `compras/templates/`, `sistema/templates/`), los mensajes de las vistas,
las etiquetas de los formularios y los mensajes de `Usuarios/validators.py`.

## Ítem 3: reglas ortográficas

| Hallazgo | Corrección | Subtarea |
|---|---|---|
| No se encontraron palabras sin tilde en el texto visible | — | G1-1239 |
| Vocabulario mezclado: "Agregar" en Usuarios y "Añadir" en Productos y Proveedores | Se usa "Agregar" en todos los botones | G1-1239 |
| "Añadir Nuevo Producto" (redundante) | "Agregar producto" | G1-1239 |
| Los mensajes de las vistas y de `validators.py` ya estaban en español y bien escritos | — | G1-1241 |

Los nombres de variables y campos del código (`telefono`, `contrasena`, `codigo`) van sin tilde
a propósito: no son texto visible y Python no admite bien las tildes en los nombres.

## Ítem 11: un solo idioma

| Texto en inglés | Corrección | Dónde |
|---|---|---|
| Dashboard | Inicio | Menú lateral y migas del panel |
| Solicitudes Admin | Solicitudes de administrador | Menú lateral |
| Panel Admin | Panel de administración | Encabezado de la tienda |
| Stock / Stock Disponible | Existencias / Existencias disponibles | Productos (plantillas y `forms.py`) |

Además, con `LANGUAGE_CODE = 'es-co'` (G1-1196) los mensajes automáticos de Django,
como "Este campo es obligatorio.", salen en español.

## Ítem 11: uso de mayúsculas

Regla: solo la primera letra en mayúscula en títulos, botones y etiquetas (guía de estilo, sección 2.3).

| Antes | Después |
|---|---|
| Nombre Completo | Nombre completo |
| Precio Normal / Precio de Oferta | Precio normal / Precio de oferta |
| Descripción Corta | Descripción corta |
| Uso e Instalación | Uso e instalación |
| Características Técnicas | Características técnicas |
| Guardar Producto / Guardar Proveedor | Guardar producto / Guardar proveedor |
| Destacado en Inicio | Destacado en inicio |
| Productos Relacionados | Productos relacionados |
| Agregar al Carrito | Agregar al carrito |
| Añadir Producto / Añadir Proveedor | Agregar producto / Agregar proveedor |
| Expertos en Iluminación | Expertos en iluminación |

## Textos que no correspondían a la función

| Antes | Después | Motivo |
|---|---|---|
| Nuevo administrador / Crear administrador / Agregar administrador | Nuevo usuario / Crear usuario / Agregar usuario | El formulario permite crear usuarios con cualquier rol |

## Pendiente

Las etiquetas de `productos/models.py` (Precio Normal, Stock Disponible, etc.) se dejaron igual
para no crear una migración nueva en la app de productos. Solo se ven en el panel `/admin/` de Django.
Queda para coordinarlo con la responsable de esa app.
