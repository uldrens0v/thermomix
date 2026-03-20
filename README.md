# Cookidoo API – TFG Thermomix

Proyecto de integración con la API no oficial de [Cookidoo](https://cookidoo.es) (plataforma de recetas de Thermomix).

## Requisitos

- Python 3.10+
- Cuenta activa en Cookidoo

Instala las dependencias:

```bash
pip install cookidoo-api python-dotenv aiohttp fastapi uvicorn jinja2 python-multipart
```

---

## Configuración: archivo `.env`

Crea un archivo `.env` en la raíz del proyecto con tus credenciales de Cookidoo:

```env
COOKIDOO_EMAIL=tu_email@ejemplo.com
COOKIDOO_PASSWORD=tu_contraseña
```


---

## Prueba con `main.py`

Ejecuta el script para verificar que la conexión con la API funciona:

```bash
python main.py
```

Realiza las siguientes acciones con tu cuenta:
- Login y verificación del usuario
- Obtención de tus listas de recetas
- Añade una receta a la lista "DIETA ANDRES" (si existe en tu cuenta)

---

## Dashboard web local

La app web permite gestionar tus listas de recetas desde el navegador.

### Iniciar el servidor

```bash
cd webapp
uvicorn app:app --host 127.0.0.1 --port 8000
```

Abre el navegador en: **http://127.0.0.1:8000**

### Funcionalidades disponibles

| Función | Descripción |
|---|---|
| **Login** | Introduce tu email y contraseña de Cookidoo |
| **Mis listas** | Visualiza todas tus colecciones de recetas |
| **Ver colección** | Consulta las recetas de cada lista |
| **Añadir receta** | Añade una receta a una lista por su ID de URL |
| **Crear receta personalizada** | Crea una copia editable de una receta oficial |
| **Eliminar receta** | Elimina una receta de una colección |
| **Nueva lista** | Crea una nueva colección personalizada |

### Cómo obtener el ID de una receta

En la URL de Cookidoo, el ID es la última parte:

```
https://cookidoo.es/recipes/recipe/es-ES/r792539
                                        ^^^^^^^^
                                        este es el ID
```

Introduce `r792539` (o solo `792539`) en el formulario de añadir receta.
