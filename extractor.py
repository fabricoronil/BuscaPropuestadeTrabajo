"""
=============================================================
 EXTRACTOR DE EMPLEOS (extractor.py)
=============================================================
 ¿Qué hace? Busca ofertas en LinkedIn Jobs y Computrabajo
 Argentina usando las palabras clave de abajo, limpia los
 datos y los guarda en 'empleos.json'.

 Cómo ejecutarlo:  python extractor.py
=============================================================
"""

import json
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ─────────────────────────────────────────────
# CONFIGURACIÓN — editá solo esta sección
# ─────────────────────────────────────────────
PALABRAS_CLAVE = ["Desarrollador", "Data", "Soporte IT"]  # qué buscar
UBICACION = "Argentina"          # ubicación para LinkedIn
MAX_POR_BUSQUEDA = 25            # tope de ofertas por palabra clave y portal
ARCHIVO_SALIDA = Path(__file__).parent / "empleos.json"

# Simulación de usuario real (evita bloqueos básicos)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def pausa_humana(min_s=1.5, max_s=3.5):
    """Espera un tiempo aleatorio, como lo haría una persona."""
    time.sleep(random.uniform(min_s, max_s))


def limpiar(texto):
    """Quita espacios raros, saltos de línea y texto sobrante."""
    if not texto:
        return ""
    return re.sub(r"\s+", " ", texto).strip()


# ─────────────────────────────────────────────
# PORTAL 1: LINKEDIN JOBS (búsqueda pública, sin login)
# ─────────────────────────────────────────────
def extraer_linkedin(page, keyword):
    """Usa la página pública de búsqueda de LinkedIn (no requiere cuenta)."""
    empleos = []
    url = (
        "https://www.linkedin.com/jobs/search?"
        f"keywords={keyword.replace(' ', '%20')}"
        f"&location={UBICACION.replace(' ', '%20')}"
        "&f_TPR=r604800"  # solo ofertas de los últimos 7 días
    )
    try:
        page.goto(url, timeout=45000, wait_until="domcontentloaded")
        pausa_humana()

        # Cada oferta es una "card" con esta clase
        tarjetas = page.locator("div.base-search-card")
        total = min(tarjetas.count(), MAX_POR_BUSQUEDA)

        for i in range(total):
            t = tarjetas.nth(i)
            try:
                titulo = limpiar(t.locator(".base-search-card__title").inner_text(timeout=3000))
                empresa = limpiar(t.locator(".base-search-card__subtitle").inner_text(timeout=2000))
                lugar = limpiar(t.locator(".job-search-card__location").inner_text(timeout=2000))
                enlace = t.locator("a.base-card__full-link").get_attribute("href", timeout=2000) or ""
                enlace = enlace.split("?")[0]  # sacamos parámetros de tracking

                # La fecha viene en el atributo datetime del tag <time>
                fecha = ""
                tiempo = t.locator("time").first
                if tiempo.count() > 0:
                    fecha = tiempo.get_attribute("datetime") or limpiar(tiempo.inner_text())

                if titulo and enlace:
                    empleos.append({
                        "titulo": titulo,
                        "empresa": empresa or "No especificada",
                        "ubicacion": lugar or UBICACION,
                        "enlace": enlace,
                        "fecha": fecha,
                        "fuente": "LinkedIn",
                        "keyword": keyword,
                    })
            except Exception:
                continue  # si una tarjeta falla, seguimos con la siguiente

    except PWTimeout:
        print(f"  [!] LinkedIn tardó demasiado para '{keyword}' (posible bloqueo temporal).")
    except Exception as e:
        print(f"  [!] LinkedIn cambió de diseño o falló para '{keyword}': {e}")

    return empleos


# ─────────────────────────────────────────────
# PORTAL 2: COMPUTRABAJO ARGENTINA
# ─────────────────────────────────────────────
def extraer_computrabajo(page, keyword):
    """Portal local líder en Argentina. Estructura HTML simple y estable."""
    empleos = []
    slug = keyword.lower().replace(" ", "-")
    url = f"https://ar.computrabajo.com/trabajo-de-{slug}"
    try:
        page.goto(url, timeout=45000, wait_until="domcontentloaded")
        pausa_humana()

        tarjetas = page.locator("article.box_offer")
        total = min(tarjetas.count(), MAX_POR_BUSQUEDA)

        for i in range(total):
            t = tarjetas.nth(i)
            try:
                link_el = t.locator("h2 a").first
                titulo = limpiar(link_el.inner_text(timeout=3000))
                href = link_el.get_attribute("href", timeout=2000) or ""
                enlace = "https://ar.computrabajo.com" + href if href.startswith("/") else href

                # Empresa: primer link con esa clase; si no existe, "Confidencial"
                empresa = "Confidencial"
                emp_el = t.locator("p a.fc_base, .fs16 a").first
                if emp_el.count() > 0:
                    empresa = limpiar(emp_el.inner_text(timeout=2000)) or empresa

                lugar = ""
                lugar_el = t.locator("p.fs16 span.mr10, p span[class*='mr10']").first
                if lugar_el.count() > 0:
                    lugar = limpiar(lugar_el.inner_text(timeout=2000))

                fecha = ""
                fecha_el = t.locator("p.fs13").first
                if fecha_el.count() > 0:
                    fecha = limpiar(fecha_el.inner_text(timeout=2000))

                if titulo and enlace:
                    empleos.append({
                        "titulo": titulo,
                        "empresa": empresa,
                        "ubicacion": lugar or "Argentina",
                        "enlace": enlace,
                        "fecha": fecha,
                        "fuente": "Computrabajo",
                        "keyword": keyword,
                    })
            except Exception:
                continue

    except PWTimeout:
        print(f"  [!] Computrabajo tardó demasiado para '{keyword}'.")
    except Exception as e:
        print(f"  [!] Computrabajo cambió de diseño o falló para '{keyword}': {e}")

    return empleos


# ─────────────────────────────────────────────
# PROGRAMA PRINCIPAL
# ─────────────────────────────────────────────
def main():
    print("=" * 50)
    print("  EXTRACTOR DE EMPLEOS — iniciando…")
    print("=" * 50)

    todos = []

    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        contexto = navegador.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 768},
            locale="es-AR",
        )
        page = contexto.new_page()

        for kw in PALABRAS_CLAVE:
            print(f"\n>> Buscando: '{kw}'")

            resultados = extraer_linkedin(page, kw)
            print(f"   LinkedIn: {len(resultados)} ofertas")
            todos += resultados
            pausa_humana(2, 5)

            resultados = extraer_computrabajo(page, kw)
            print(f"   Computrabajo: {len(resultados)} ofertas")
            todos += resultados
            pausa_humana(2, 5)

        navegador.close()

    # ── Limpieza final: eliminar duplicados por enlace ──
    vistos = set()
    unicos = []
    for e in todos:
        if e["enlace"] not in vistos:
            vistos.add(e["enlace"])
            unicos.append(e)

    salida = {
        "actualizado": datetime.now(timezone.utc).isoformat(),
        "total": len(unicos),
        "empleos": unicos,
    }

    ARCHIVO_SALIDA.write_text(
        json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n" + "=" * 50)
    print(f"  LISTO: {len(unicos)} ofertas guardadas en {ARCHIVO_SALIDA.name}")
    print("=" * 50)


if __name__ == "__main__":
    main()
