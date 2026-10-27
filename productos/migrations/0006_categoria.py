import django.db.models.deletion
from django.db import migrations, models

# Las 4 categorías que existían como lista fija en el código (valor antiguo -> nombre)
CATEGORIAS_INICIALES = {
    'electricos': 'Eléctricos',
    'interiores': 'Interiores',
    'ferreteria': 'Ferretería',
    'iluminacion': 'Iluminación',
}


def copiar_categorias(apps, schema_editor):
    """Crea las categorías y enlaza cada producto existente con la suya (no se pierde nada)."""
    Categoria = apps.get_model('productos', 'Categoria')
    Producto = apps.get_model('productos', 'Producto')

    creadas = {}
    for valor, nombre in CATEGORIAS_INICIALES.items():
        creadas[valor] = Categoria.objects.get_or_create(nombre=nombre)[0]

    for producto in Producto.objects.all():
        categoria = creadas.get(producto.categoria)
        if categoria is None:  # valor inesperado en la base de datos: se crea tal cual
            categoria = Categoria.objects.get_or_create(nombre=producto.categoria.capitalize())[0]
            creadas[producto.categoria] = categoria
        Producto.objects.filter(pk=producto.pk).update(categoria_nueva=categoria)


def devolver_categorias(apps, schema_editor):
    """Al deshacer la migración: vuelve a escribir el valor antiguo en cada producto."""
    Producto = apps.get_model('productos', 'Producto')
    inverso = {nombre: valor for valor, nombre in CATEGORIAS_INICIALES.items()}
    for producto in Producto.objects.select_related('categoria_nueva'):
        valor = inverso.get(producto.categoria_nueva.nombre, 'electricos') if producto.categoria_nueva else 'electricos'
        Producto.objects.filter(pk=producto.pk).update(categoria=valor)


class Migration(migrations.Migration):

    dependencies = [
        ('productos', '0005_proveedor_inactivacion'),
    ]

    operations = [
        migrations.CreateModel(
            name='Categoria',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=60, unique=True, verbose_name='Nombre')),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Categoría',
                'verbose_name_plural': 'Categorías',
                'ordering': ['nombre'],
            },
        ),
        # 1) columna nueva, temporal y opcional
        migrations.AddField(
            model_name='producto',
            name='categoria_nueva',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='productos.categoria'),
        ),
        # 2) copiar los datos
        migrations.RunPython(copiar_categorias, devolver_categorias),
        # 3) quitar la columna antigua (texto) y poner la nueva en su lugar
        migrations.RemoveField(model_name='producto', name='categoria'),
        migrations.RenameField(model_name='producto', old_name='categoria_nueva', new_name='categoria'),
        migrations.AlterField(
            model_name='producto',
            name='categoria',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='productos', to='productos.categoria'),
        ),
    ]