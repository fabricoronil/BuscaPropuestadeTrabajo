"""
=============================================================
 EXTRACTOR DE EMPLEOS PERSONALIZADO (extractor.py)
=============================================================
 Perfil: estudiante de Ing. en Sistemas (19 años, 2do año),
 certificado Full Stack: React, TypeScript, Tailwind,
 Node.js, MongoDB, SQL/NoSQL, Git/GitHub.

 - Busca en 5 portales (LinkedIn, Computrabajo, Bumeran,
   ZonaJobs, RemoteOK)
 - Solo Misiones/Posadas o 100% remoto
 - Puntúa afinidad 0-100 según tu perfil y tu stack
 - Entra a las mejores ofertas y trae la descripción
   completa para verla en la web sin abrir el link

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
PALABRAS_CLAVE = ["Pasantía", "Trainee", "Junior", "React", "Node.js", "Full Stack"]

CIUDADES = ["misiones", "posadas"]   # zona presencial aceptada

MAX_POR_BUSQUEDA = 15
TOP_CON_DESCRIPCION = 40   # a cuántas ofertas (las mejores) les traemos la descripción
ARCHIVO_SALIDA = Path(__file__).parent / "empleos.json"

# Tu stack: si la oferta lo menciona, sube el porcentaje
TECNOLOGIAS = {
    "React":      r"\breact\b",
    "TypeScript": r"\btypescript\b",
    "Tailwind":   r"\btailwind",
    "Node.js":    r"\bnode(\.js|js)?\b",
    "MongoDB":    r"\bmongo(db)?\b",
    "SQL":        r"\b(my)?sql\b|\bpostgres",
    "JavaScript": r"\bjavascript\b",
    "Git":        r"\bgit(hub)?\b",
    "Full Stack": r"\bfull[\s-]?stack\b",
    "Front End":  r"\bfront[\s-]?end\b",
    "Back End":   r"\bback[\s-]?end\b",
}

PISTAS_REMOTO = ["remoto", "remote", "teletrabajo", "home office", "homeoffice",
                 "desde casa", "wfh", "anywhere", "trabajo a distancia"]

IDEAL_PARA_EMPEZAR = ["pasantía", "pasantia", "trainee", "intern", "internship",
                      "junior", "jr.", "jr ", "sin experiencia", "primer empleo",
                      "aprendiz", "becario", "practicante", "entry level", "entry-level",
                      "estudiante"]

MEDIO_TIEMPO = ["part time", "part-time", "medio tiempo", "media jornada",
                "4 horas", "4 hs", "jornada reducida", "por horas"]

PIDE_INGLES = ["inglés avanzado", "ingles avanzado", "inglés fluido", "ingles fluido",
               "english required", "fluent english", "advanced english",
               "inglés intermedio", "ingles intermedio", "bilingüe", "bilingue"]

EXCLUIR_SENIORIDAD = r"\b(senior|ssr|sr\.?|semi[\s-]?senior|lead|jefe|jefa|gerente|manager|head|arquitecto|director|supervisor)\b"

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


def detectar_techs(texto):
    """Devuelve la lista de tecnologías de TU stack mencionadas en el texto."""
    return [nombre for nombre, patron in TECNOLOGIAS.items() if re.search(patron, texto)]


# ═════════════════════════════════════════════
# PUNTAJE DE AFINIDAD (0-100)
# ═════════════════════════════════════════════
def puntuar(e):
    texto = f"{e['titulo']} {e['ubicacion']} {e.get('texto_card', '')}".lower()
    motivos = []

    if re.search(EXCLUIR_SENIORIDAD, texto):
        return None

    es_remoto = e.get("es_remoto", False) or any(p in texto for p in PISTAS_REMOTO)
    en_zona = any(c in texto for c in CIUDADES)
    if not (es_remoto or en_zona):
        return None

    puntos = 45  # base

    if en_zona:
        puntos += 15
        motivos.append("✓ Misiones/Posadas")
    if es_remoto:
        puntos += 12
        motivos.append("✓ Remoto")

    if any(p in texto for p in IDEAL_PARA_EMPEZAR):
        puntos += 18
        motivos.append("✓ Ideal para empezar (trainee/jr/pasantía)")

    if any(p in texto for p in MEDIO_TIEMPO):
        puntos += 10
        motivos.append("✓ Medio tiempo")

    techs = detectar_techs(texto)
    if techs:
        puntos += min(22, 5 * len(techs))
        motivos.append("✓ Tu stack: " + ", ".join(techs[:5]))

    exp = re.search(r"(\d+)\s*(años|año|years|yrs)", texto)
    if exp and "sin experiencia" not in texto:
        puntos -= 18
        motivos.append(f"− Pide {exp.group(1)}+ años de experiencia")

    if any(p in texto for p in PIDE_INGLES):
        puntos -= 15
        motivos.append("− Pide inglés")
    elif e.get("fuente_en_ingles") or any(p in e["titulo"].lower() for p in PALABRAS_EN_INGLES):
        puntos -= 8
        motivos.append("− Publicación en inglés")

    e["afinidad"] = max(5, min(98, puntos))
    e["motivos"] = motivos
    e["es_remoto"] = es_remoto
    e["techs"] = techs
    e.pop("texto_card", None)
    e.pop("fuente_en_ingles", None)
    return e


# ═════════════════════════════════════════════
# ENRIQUECER: entrar a la oferta y traer la descripción
# ═════════════════════════════════════════════
SELECTORES_DESCRIPCION = [
    "div.show-more-less-html__markup",      # LinkedIn
    ".description__text",                    # LinkedIn (alternativo)
    "div[class*='description']",             # genérico
    "div.fs16.t_word_wrap",                  # Computrabajo
    "section#description",
    "article",
]


def enriquecer(page, e):
    """Visita la oferta y guarda su descripción + re-puntúa con más datos."""
    if e.get("descripcion"):
        return
    try:
        page.goto(e["enlace"], timeout=30000, wait_until="domcontentloaded")
        pausa_humana(1, 2)
        desc = ""
        for sel in SELECTORES_DESCRIPCION:
            loc = page.locator(sel).first
            if loc.count() > 0:
                candidato = limpiar(loc.inner_text(timeout=3000))
                if len(candidato) > 150:
                    desc = candidato
                    break
        if not desc:
            return
        e["descripcion"] = desc[:1800]
        texto = desc.lower()

        # Nuevas tecnologías encontradas en la descripción
        nuevas = [t for t in detectar_techs(texto) if t not in e["techs"]]
        if nuevas:
            e["techs"] += nuevas
            e["afinidad"] = min(98, e["afinidad"] + 3 * len(nuevas))
            e["motivos"] = [m for m in e["motivos"] if not m.startswith("✓ Tu stack")]
            e["motivos"].append("✓ Tu stack: " + ", ".join(e["techs"][:6]))

        # Penalizaciones que solo se ven en la descripción
        if not any("experiencia" in m for m in e["motivos"]):
            exp = re.search(r"(\d+)\s*(años|año|years|yrs)", texto)
            if exp and "sin experiencia" not in texto:
                e["afinidad"] = max(5, e["afinidad"] - 12)
                e["motivos"].append(f"− Pide {exp.group(1)}+ años de experiencia")
        if not any("inglés" in m.lower() for m in e["motivos"]):
            if any(p in texto for p in PIDE_INGLES):
                e["afinidad"] = max(5, e["afinidad"] - 10)
                e["motivos"].append("− Pide inglés")
    except Exception:
        pass  # si no se puede, la tarjeta queda sin descripción y listo


# ═════════════════════════════════════════════
# PORTAL 1: LINKEDIN
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
        url += "&f_WT=2"
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
# PORTAL 2: COMPUTRABAJO ARGENTINA
# ═════════════════════════════════════════════
def extraer_computrabajo(page, keyword, sufijo=""):
    empleos = []
    slug = keyword.lower().replace(" ", "-").replace("í", "i").replace("é", "e").replace(".", "")
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
# PORTALES 3 y 4: BUMERAN y ZONAJOBS
# ═════════════════════════════════════════════
def extraer_bumeran_zonajobs(page, keyword, dominio, nombre):
    empleos = []
    slug = keyword.lower().replace(" ", "-").replace("í", "i").replace("é", "e").replace(".", "")
    url = f"https://www.{dominio}/empleos-busqueda-{slug}.html"
    try:
        page.goto(url, timeout=45000, wait_until="networkidle")
        pausa_humana(2, 4)
        tarjetas = page.locator("a[href*='/empleos/']")
        agregados = 0
        for i in range(tarjetas.count()):
            if agregados >= MAX_POR_BUSQUEDA:
                break
            t = tarjetas.nth(i)
            try:
                href = t.get_attribute("href", timeout=1500) or ""
                if not re.search(r"/empleos/.+\d+\.html?$", href):
                    continue
                texto = limpiar(t.inner_text(timeout=1500))
                if len(texto) < 15:
                    continue
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
# PORTAL 5: REMOTEOK (API pública, trae descripción incluida)
# ═════════════════════════════════════════════
def extraer_remoteok(page):
    empleos = []
    try:
        page.goto("https://remoteok.com/api", timeout=45000)
        crudo = page.evaluate("() => document.body.innerText")
        datos = json.loads(crudo)
        filtros = ["junior", "intern", "trainee", "entry", "react", "node",
                   "javascript", "typescript", "full stack", "fullstack"]
        for item in datos:
            if not isinstance(item, dict) or not item.get("position"):
                continue
            texto = (item.get("position", "") + " " + " ".join(item.get("tags", []))).lower()
            if not any(f in texto for f in filtros):
                continue
            desc = re.sub(r"<[^>]+>", " ", item.get("description", "") or "")
            empleos.append({
                "titulo": limpiar(item["position"]),
                "empresa": limpiar(item.get("company", "")) or "No especificada",
                "ubicacion": limpiar(item.get("location", "")) or "Remoto mundial",
                "enlace": item.get("url", ""),
                "fecha": (item.get("date", "") or "")[:10],
                "fuente": "RemoteOK", "keyword": "remoto",
                "es_remoto": True, "fuente_en_ingles": True,
                "descripcion": limpiar(desc)[:1800],
                "texto_card": (limpiar(desc)[:280] or texto[:280]),
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

        # ── Deduplicar ──
        vistos, unicos = set(), []
        for e in todos:
            if e["enlace"] and e["enlace"] not in vistos:
                vistos.add(e["enlace"])
                unicos.append(e)

        # ── Puntuar y filtrar según tu perfil ──
        finales, descartados = [], 0
        for e in unicos:
            resultado = puntuar(e)
            if resultado:
                finales.append(resultado)
            else:
                descartados += 1

        finales.sort(key=lambda x: x["afinidad"], reverse=True)

        # ── Traer la descripción de las mejores ofertas ──
        candidatas = [e for e in finales if not e.get("descripcion")][:TOP_CON_DESCRIPCION]
        print(f"\n>> Trayendo descripción completa de las {len(candidatas)} mejores ofertas…")
        for i, e in enumerate(candidatas, 1):
            enriquecer(page, e)
            if i % 10 == 0:
                print(f"   {i}/{len(candidatas)}…")

        navegador.close()

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
    print(f"  LISTO: {len(finales)} ofertas para tu perfil")
    print(f"  (descartadas {descartados}: seniors o fuera de zona sin remoto)")
    print("=" * 52)


if __name__ == "__main__":
    main()
