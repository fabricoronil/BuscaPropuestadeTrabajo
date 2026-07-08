# 💼 Mis Empleos — Agregador automático de ofertas

Sistema 100% gratuito que busca empleos en **LinkedIn** y **Computrabajo Argentina**, los muestra en una web propia y se actualiza solo.

## Archivos

| Archivo | Qué hace |
|---|---|
| `extractor.py` | Busca las ofertas y genera `empleos.json` |
| `index.html` | La página web que muestra las ofertas |
| `deploy.py` | Ejecuta el extractor y sube los cambios a GitHub |
| `empleos.json` | Los datos (se regenera solo) |

## Puesta en marcha desde cero (Windows)

### 1. Instalar requisitos (una sola vez)

Necesitás [Python](https://www.python.org/downloads/) (marcá "Add to PATH" al instalar) y [Git](https://git-scm.com/download/win).

Abrí una terminal (PowerShell) **dentro de esta carpeta** y ejecutá:

```powershell
pip install -r requirements.txt
playwright install chromium
```

### 2. Probar el extractor

```powershell
python extractor.py
```

Debería crear `empleos.json`. Para ver la web localmente:

```powershell
python -m http.server 8000
```

Y abrí http://localhost:8000 en el navegador.

> ⚠ No abras `index.html` con doble clic: el `fetch()` de JSON solo funciona a través de un servidor (local o en internet).

### 3. Subir a GitHub (una sola vez)

Creá un repositorio vacío en https://github.com/new (por ejemplo `mis-empleos`) y luego:

```powershell
git init
git add .
git commit -m "Primer commit"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/mis-empleos.git
git push -u origin main
```

### 4. Publicar la web gratis

**Opción A — Cloudflare Pages** (recomendada): en https://dash.cloudflare.com → Workers & Pages → Create → Pages → Connect to Git → elegí tu repo → Build command: *(vacío)* → Output directory: `/` → Deploy.

**Opción B — Netlify**: en https://app.netlify.com → Add new site → Import from Git → elegí tu repo → Deploy (sin build command).

Cada `git push` actualizará la web automáticamente en 1-2 minutos.

### 5. Actualizar las ofertas

Cada vez que quieras refrescar:

```powershell
python deploy.py
```

### 6. (Opcional) Automatizar del todo con el Programador de tareas de Windows

1. Abrí "Programador de tareas" → *Crear tarea básica*.
2. Nombre: `Actualizar empleos` → Desencadenador: *Diariamente* a la hora que prefieras.
3. Acción: *Iniciar un programa* →
   - Programa: `python`
   - Argumentos: `deploy.py`
   - Iniciar en: la ruta completa de esta carpeta.

Listo: la web se actualiza sola todos los días sin tocar nada.

## Personalización

- **Palabras clave y ubicación**: editá `PALABRAS_CLAVE` y `UBICACION` al inicio de `extractor.py`.
- **Cantidad de resultados**: cambiá `MAX_POR_BUSQUEDA`.

## Notas importantes

- **Frecuencia segura: 1 vez al día (máximo 2).** El extractor usa pausas humanas aleatorias, user-agent rotativo, caché de descripciones (no repite visitas) y detección de captcha: si un portal lo frena, lo saltea y sigue con los demás. Los bloqueos de este tipo son temporales (horas), no permanentes.
- Si un portal cambia su diseño, el script no se rompe: avisa por consola y sigue con el resto.
- Revisá los términos de uso de cada portal; este proyecto es para uso personal.
