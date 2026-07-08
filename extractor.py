"""
=============================================================
 EXTRACTOR DE EMPLEOS PERSONALIZADO (extractor.py)
=============================================================
 Busca ofertas en 5 portales, calcula qué tanto se ajusta
 cada una a TU PERFIL (0-100%) y descarta las que no sirven:
 - Solo Misiones/Posadas o 100% remoto
 - Prioriza pasantías, trainee, junior, medio tiempo
 - Penaliza (pero muestra) las que piden inglés

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

# ═════════════════════════════════════════════
# TU PERFIL — editá esta sección a gusto
# ═════════════════════════════════════════════
PALABRAS_CLAVE = ["Pasantía", "Trainee", "Junior", "Soporte IT", "Desarrollador"]

CIUDADES = ["misiones", "posadas"]   # zona presencial aceptada
# Si la oferta NO es de estas ciudades y NO dice que es remota → se descarta.

MAX_POR_BUSQUEDA = 15
ARCHIVO_SALIDA = Path(__file__).parent / "empleos.json"

# ── Diccionarios que usa el puntaje ──
PISTAS_REMOTO = ["remoto", "remote", "teletrabajo", "home office", "homeoffice",
                 "desde casa", "wfh", "anywhere", "trabajo a distancia"]

IDEAL_PARA_EMPEZAR = ["pasantía", "pasantia", "trainee", "intern", "internship",
                      "junior", "jr.", "jr ", "sin experiencia", "primer empleo",
                      "aprendiz", "becario", "practicante", "entry level", "entry-level"]

MEDIO_TIEMPO = ["part time", "part-time", "medio tiempo", "media jornada",
                "4 horas", "4 hs", "jornada reducida", "por horas"]

PIDE_INGLES = ["inglés avanzado", "ingles avanzado", "inglés fluido", "ingles fluido",
               "english required", "fluent english", "advanced english",
               "inglés intermedio", "ingles intermedio", "bilingüe", "bilingue"]

# Ofertas con estos términos se DESCARTAN (buscan gente con experiencia)
EXCLUIR_SENIORIDAD = r"\b(senior|ssr|sr\.?|semi[\s-]?senior|lead|jefe|jefa|gerente|manager|head|arquitecto|director|supervisor)\b"

# Palabras típicas de títulos en inglés (para detectar publicaciones en inglés)
PALABRAS_EN_INGLES = ["developer", "engineer", "support specialist", "analyst",
                      "assistant", "designer", "software", "customer", "agent"]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def pausa_humana(min_s=1.5, max_s=3.5):
    time.sleep(random.uniform(min_s, max_s))


def limpiar(texto):
    if not texto:
        return ""
    return re.sub(r"\s+", " ", texto).strip()


# ═════════════════════════════════════════════
# PUNTAJE DE AFINIDAD (0-100)
# Devuelve None si la oferta debe descartarse.
# ═════════════════════════════════════════════
def puntuar(e):
    texto = f"{e['titulo']} {e['ubicacion']} {e.get('texto_card', '')}".lower()
    motivos = []

    # ── DESCARTE 1: piden seniority alto ──
    if re.search(EXCLUIR_SENIORIDAD, texto):
        return None

    # ── DESCARTE 2: ni es de tu zona ni es remoto ──
    es_remoto = e.get("es_remoto", False) or any(p in texto for p in PISTAS_REMOTO)
    en_zona = any(c in texto for c in CIUDADES)
    if not (es_remoto or en_zona):
        return None

    puntos = 50  # base

    if en_zona:
        puntos += 18
        motivos.append("✓ Misiones/Posadas")
    if es_remoto:
        puntos += 14
        motivos.append("✓ Remoto")

    if any(p in texto for p in IDEAL_PARA_EMPEZAR):
        puntos += 22
        motivos.append("✓ Ideal para empezar (trainee/jr/pasantía)")

    if any(p in texto for p in MEDIO_TIEMPO):
        puntos += 12
        motivos.append("✓ Medio tiempo")

    # Penalización: piden años de experiencia (salvo que diga "sin experiencia")
    exp = re.search(r"(\d+)\s*(años|año|years|yrs)", texto)
    if exp and "sin experiencia" not in texto:
        puntos -= 20
        motivos.append(f"− Pide {exp.group(1)}+ años de experiencia")

    # Penalización: inglés
    if any(p in texto for p in PIDE_INGLES):
        puntos -= 15
        motivos.append("− Pide inglés")
    elif e.get("fuente_en_ingles") or any(p in e["titulo"].lower() for p in PALABRAS_EN_INGLES):
        puntos -= 8
        motivos.append("− Publicación en inglés")

    puntos = max(5, min(98, puntos))
    e["afinidad"] = puntos
    e["motivos"] = motivos
    e["es_remoto"] = es_remoto
    e.pop("texto_card", None)      # no guardamos el texto crudo en el JSON
    e.pop("fuente_en_ingles", None)
    return e


# ═════════════════════════════════════════════
# PORTAL 1: LINKEDIN (2 búsquedas: Misiones + remoto Argentina)
# ═════════════════════════════════════════════
def extraer_linkedin(page, keyword, ubicacion, solo_remoto):
    empleos = []
    url = (
        "https://www.linkedin.com/jobs/search?"
        f"keywords={keyword.replace(' ', '%20')}"
        f"&location={ubicacion.replace(' ', '%20')}"
        "&f_TPR=r604800"
    )
    if solo_remoto:
        url += "&f_WT=2"  # filtro oficial de LinkedIn: solo remoto
    try:
        page.goto(url, timeout=45000, wait_until="domcontentloaded")
        pausa_humana()
        tarjetas = page.locator("div.base-search-card")
        for i in range(min(tarjetas.count(), MAX_POR_BUSQUEDA)):
            t = tarjetas.nth(i)
            try:
                titulo = limpiar(t.locator(".base-search-card__title").inner_text(timeout=3000))
                empresa = limpiar(t.locator(".base-search-card__subtitle").inner_text(timeout=2000))
                lugar = limpiar(t.locator(".job-search-card__location").inner_text(timeout=2000))
                enlace = (t.locator("a.base-card__full-link").get_attribute("href", timeout=2000) or "").split("?")[0]
                fecha = ""
                tiempo = t.locator("time").first
                if tiempo.count() > 0:
                    fecha = tiempo.get_attribute("datetime") or limpiar(tiempo.inner_text())
                if titulo and enlace:
                    empleos.append({
                        "titulo": titulo, "empresa": empresa or "No especificada",
                        "ubicacion": lugar or ubicacion, "enlace": enlace, "fecha": fecha,
                        "fuente": "LinkedIn", "keyword": keyword,
                        "es_remoto": solo_remoto,
                        "texto_card": limpiar(t.inner_text(timeout=2000))[:300],
                    })
            except Exception:
                continue
    except Exception as ex:
        print(f"  [!] LinkedIn falló ({keyword}): {type(ex).__name__}")
    return empleos


# ═════════════════════════════════════════════
# PORTAL 2: COMPUTRABAJO ARGENTINA (Misiones + remoto)
# ═════════════════════════════════════════════
def extraer_computrabajo(page, keyword, sufijo=""):
    """sufijo: '-en-misiones' para la zona, '' para búsqueda general."""
    empleos = []
    slug = keyword.lower().replace(" ", "-").replace("í", "i").replace("é", "e")
    url = f"https://ar.computrabajo.com/trabajo-de-{slug}{sufijo}"
    try:
        page.goto(url, timeout=45000, wait_until="domcontentloaded")
        pausa_humana()
        tarjetas = page.locator("article.box_offer")
        for i in range(min(tarjetas.count(), MAX_POR_BUSQUEDA)):
            t = tarjetas.nth(i)
            try:
                link_el = t.locator("h2 a").first
                titulo = limpiar(link_el.inner_text(timeout=3000))
                href = link_el.get_attribute("href", timeout=2000) or ""
                enlace = "https://ar.computrabajo.com" + href if href.startswith("/") else href
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
                        "titulo": titulo, "empresa": empresa,
                        "ubicacion": lugar or "Argentina", "enlace": enlace, "fecha": fecha,
                        "fuente": "Computrabajo", "keyword": keyword,
                        "texto_card": limpiar(t.inner_text(timeout=2000))[:300],
                    })
            except Exception:
                continue
    except Exception as ex:
        print(f"  [!] Computrabajo falló ({keyword}{sufijo}): {type(ex).__name__}")
    return empleos


# ═════════════════════════════════════════════
# PORTAL 3 y 4: BUMERAN y ZONAJOBS (misma plataforma)
# ═════════════════════════════════════════════
def extraer_bumeran_zonajobs(page, keyword, dominio, nombre):
    empleos = []
    slug = keyword.lower().replace(" ", "-").replace("í", "i").replace("é", "e")
    url = f"https://www.{dominio}/empleos-busqueda-{slug}.html"
    try:
        page.goto(url, timeout=45000, wait_until="networkidle")
        pausa_humana(2, 4)
        # Los avisos son links cuyo href contiene '/empleos/'
        tarjetas = page.locator("a[href*='/empleos/']")
        agregados = 0
        for i in range(tarjetas.count()):
            if agregados >= MAX_POR_BUSQUEDA:
                break
            t = tarjetas.nth(i)
            try:
                href = t.get_attribute("href", timeout=1500) or ""
                if not re.search(r"/empleos/.+\d+\.html?$", href):
                    continue  # descartamos links de menú/categorías
                texto = limpiar(t.inner_text(timeout=1500))
                if len(texto) < 15:
                    continue
                # El título suele ser el primer h2/h3 dentro del link
                titulo = texto
                th = t.locator("h2, h3").first
                if th.count() > 0:
                    titulo = limpiar(th.inner_text(timeout=1500))
                enlace = href if href.startswith("http") else f"https://www.{dominio}{href}"
                empleos.append({
                    "titulo": titulo[:120], "empresa": "Ver aviso",
                    "ubicacion": "Argentina", "enlace": enlace, "fecha": "",
                    "fuente": nombre, "keyword": keyword,
                    "texto_card": texto[:300],
                })
                agregados += 1
            except Exception:
                continue
    except Exception as ex:
        print(f"  [!] {nombre} falló ({keyword}): {type(ex).__name__}")
    return empleos


# ═════════════════════════════════════════════
# PORTAL 5: REMOTEOK (API pública, 100% remoto, en inglés)
# ═════════════════════════════════════════════
def extraer_remoteok(page):
    empleos = []
    try:
        page.goto("https://remoteok.com/api", timeout=45000)
        crudo = page.evaluate("() => document.body.innerText")
        datos = json.loads(crudo)
        filtros = ["junior", "intern", "trainee", "entry", "support", "data"]
        for item in datos:
            if not isinstance(item, dict) or not item.get("position"):
                continue
            texto = (item.get("position", "") + " " + " ".join(item.get("tags", []))).lower()
            if not any(f in texto for f in filtros):
                continue
            empleos.append({
                "titulo": limpiar(item["position"]),
                "empresa": limpiar(item.get("company", "")) or "No especificada",
                "ubicacion": limpiar(item.get("location", "")) or "Remoto mundial",
                "enlace": item.get("url", ""),
                "fecha": (item.get("date", "") or "")[:10],
                "fuente": "RemoteOK", "keyword": "remoto",
                "es_remoto": True, "fuente_en_ingles": True,
                "texto_card": texto[:300],
            })
            if len(empleos) >= 20:
                break
    except Exception as ex:
        print(f"  [!] RemoteOK falló: {type(ex).__name__}")
    return empleos


# ═════════════════════════════════════════════
# PROGRAMA PRINCIPAL
# ═════════════════════════════════════════════
def main():
    print("=" * 52)
    print("  EXTRACTOR PERSONALIZADO — iniciando…")
    print("=" * 52)

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

            r = extraer_linkedin(page, kw, "Misiones, Argentina", solo_remoto=False)
            print(f"   LinkedIn Misiones: {len(r)}")
            todos += r
            pausa_humana(2, 4)

            r = extraer_linkedin(page, kw, "Argentina", solo_remoto=True)
            print(f"   LinkedIn remoto: {len(r)}")
            todos += r
            pausa_humana(2, 4)

            r = extraer_computrabajo(page, kw, "-en-misiones")
            print(f"   Computrabajo Misiones: {len(r)}")
            todos += r
            pausa_humana(2, 4)

            r = extraer_computrabajo(page, kw + " remoto")
            print(f"   Computrabajo remoto: {len(r)}")
            todos += r
            pausa_humana(2, 4)

            r = extraer_bumeran_zonajobs(page, kw, "bumeran.com.ar", "Bumeran")
            print(f"   Bumeran: {len(r)}")
            todos += r
            pausa_humana(2, 4)

            r = extraer_bumeran_zonajobs(page, kw, "zonajobs.com.ar", "ZonaJobs")
            print(f"   ZonaJobs: {len(r)}")
            todos += r
            pausa_humana(2, 4)

        print("\n>> RemoteOK (remotos internacionales)…")
        r = extraer_remoteok(page)
        print(f"   RemoteOK: {len(r)}")
        todos += r

        navegador.close()

    # ── Deduplicar por enlace ──
    vistos, unicos = set(), []
    for e in todos:
        if e["enlace"] and e["enlace"] not in vistos:
            vistos.add(e["enlace"])
            unicos.append(e)

    # ── Puntuar según TU perfil y descartar lo que no aplica ──
    finales = []
    descartados = 0
    for e in unicos:
        resultado = puntuar(e)
        if resultado:
            finales.append(resultado)
        else:
            descartados += 1

    finales.sort(key=lambda x: x["afinidad"], reverse=True)

    salida = {
        "actualizado": datetime.now(timezone.utc).isoformat(),
        "total": len(finales),
        "empleos": finales,
    }
    ARCHIVO_SALIDA.write_text(
        json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n" + "=" * 52)
    print(f"  LISTO: {len(finales)} ofertas que se ajustan a tu perfil")
    print(f"  (se descartaron {descartados}: seniors o fuera de zona sin remoto)")
    print("=" * 52)


if __name__ == "__main__":
    main()
