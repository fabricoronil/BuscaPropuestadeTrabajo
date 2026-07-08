"""
=============================================================
 EXTRACTOR DE EMPLEOS PERSONALIZADO (extractor.py)  v3
=============================================================
 Perfil: estudiante de Ing. en Sistemas (19 años, 2do año),
 certificado Full Stack: React, TypeScript, Tailwind,
 Node.js, MongoDB, SQL/NoSQL, Git/GitHub.

 Novedades v3 (auditoría):
 - Anti-bloqueo: pausas humanas más largas y variables,
   user-agent rotativo, zona horaria y idioma argentinos,
   detección de captcha/bloqueo (corta ese portal y sigue).
 - Caché inteligente: recuerda las ofertas anteriores, así
   NO vuelve a visitar descripciones que ya tiene (menos
   requests = menos riesgo de bloqueo) y las ofertas nuevas
   se marcan como "NUEVO" en la web.
 - Menos carga: no descarga imágenes ni fuentes.

 Cómo ejecutarlo:  python extractor.py
 Frecuencia recomendada: 1 vez al día (máximo 2).
=============================================================
"""

import json
import random
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ═════════════════════════════════════════════
# TU PERFIL — editá esta sección a gusto
# ═════════════════════════════════════════════
PALABRAS_CLAVE = ["Pasantía", "Trainee", "Junior", "React", "Node.js", "Full Stack"]

CIUDADES = ["misiones", "posadas"]

MAX_POR_BUSQUEDA = 15
TOP_CON_DESCRIPCION = 25      # visitas máximas a páginas de detalle por corrida
DIAS_RETENER_OFERTA = 12      # cuántos días conservar una oferta que ya no aparece
ARCHIVO_SALIDA = Path(__file__).parent / "empleos.json"

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

# ═════════════════════════════════════════════
# ANTI-BLOQUEO
# ═════════════════════════════════════════════
USER_AGENTS = [
    # Chrome y Edge recientes en Windows (los más comunes en Argentina)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
]

SEÑALES_BLOQUEO = ["captcha", "unusual activity", "actividad inusual", "are you a robot",
                   "verify you are human", "access denied", "has sido bloqueado",
                   "challenge-platform", "cf-challenge", "authwall"]

# Portales que detectamos bloqueados en esta corrida (los salteamos)
bloqueados = set()


def pausa_humana(min_s=2.5, max_s=6.0):
    """Pausa aleatoria estilo humano. A veces una pausa extra larga (como
    alguien que se distrae), lo que hace el patrón menos robótico."""
    t = random.uniform(min_s, max_s)
    if random.random() < 0.08:
        t += random.uniform(4, 9)
    time.sleep(t)


def limpiar(texto):
    if not texto:
        return ""
    return re.sub(r"\s+", " ", texto).strip()


def parece_bloqueo(page):
    """Detecta si el portal nos mostró un captcha o pantalla de bloqueo."""
    try:
        contenido = (page.title() + " " + page.url).lower()
        if any(s in contenido for s in SEÑALES_BLOQUEO):
            return True
        cuerpo = page.locator("body").inner_text(timeout=3000)[:600].lower()
        return any(s in cuerpo for s in SEÑALES_BLOQUEO)
    except Exception:
        return False


def navegar(page, url, portal, espera="domcontentloaded", timeout=45000):
    """Navega con 1 reintento y detección de bloqueo.
    Devuelve False si el portal está bloqueado o no responde."""
    if portal in bloqueados:
        return False
    for intento in (1, 2):
        try:
            page.goto(url, timeout=timeout, wait_until=espera)
            pausa_humana(1.5, 3.0)
            # scroll suave, como un humano que mira la página
            page.mouse.wheel(0, random.randint(300, 900))
            time.sleep(random.uniform(0.4, 1.2))
            if parece_bloqueo(page):
                print(f"  [!] {portal}: posible bloqueo/captcha detectado. "
                      f"Salteamos este portal por hoy (se le pasa solo).")
                bloqueados.add(portal)
                return False
            return True
        except PWTimeout:
            if intento == 1:
                time.sleep(random.uniform(5, 10))
                continue
            print(f"  [!] {portal}: no respondió a tiempo.")
            return False
        except Exception as ex:
            print(f"  [!] {portal}: error de navegación ({type(ex).__name__}).")
            return False
    return False


def detectar_techs(texto):
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

    puntos = 45
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


def aplicar_descripcion(e, desc):
    """Suma la información de la descripción al puntaje (compartido entre
    la visita en vivo y la reutilización desde el caché)."""
    e["descripcion"] = desc[:1800]
    texto = desc.lower()

    nuevas = [t for t in detectar_techs(texto) if t not in e["techs"]]
    if nuevas:
        e["techs"] += nuevas
        e["afinidad"] = min(98, e["afinidad"] + 3 * len(nuevas))
        e["motivos"] = [m for m in e["motivos"] if not m.startswith("✓ Tu stack")]
        e["motivos"].append("✓ Tu stack: " + ", ".join(e["techs"][:6]))

    if not any("experiencia" in m for m in e["motivos"]):
        exp = re.search(r"(\d+)\s*(años|año|years|yrs)", texto)
        if exp and "sin experiencia" not in texto:
            e["afinidad"] = max(5, e["afinidad"] - 12)
            e["motivos"].append(f"− Pide {exp.group(1)}+ años de experiencia")
    if not any("inglés" in m.lower() for m in e["motivos"]):
        if any(p in texto for p in PIDE_INGLES):
            e["afinidad"] = max(5, e["afinidad"] - 10)
            e["motivos"].append("− Pide inglés")


SELECTORES_DESCRIPCION = [
    "div.show-more-less-html__markup",
    ".description__text",
    "div[class*='description']",
    "div.fs16.t_word_wrap",
    "section#description",
    "article",
]


def enriquecer(page, e):
    """Visita la oferta y trae la descripción (solo si no la tenemos)."""
    if e.get("descripcion"):
        return
    portal = e["fuente"]
    if not navegar(page, e["enlace"], portal, timeout=30000):
        return
    try:
        desc = ""
        for sel in SELECTORES_DESCRIPCION:
            loc = page.locator(sel).first
            if loc.count() > 0:
                candidato = limpiar(loc.inner_text(timeout=3000))
                if len(candidato) > 150:
                    desc = candidato
                    break
        if desc:
            aplicar_descripcion(e, desc)
    except Exception:
        pass


# ═════════════════════════════════════════════
# PORTALES
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
    if not navegar(page, url, "LinkedIn"):
        return empleos
    try:
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


def extraer_computrabajo(page, keyword, sufijo=""):
    empleos = []
    slug = keyword.lower().replace(" ", "-").replace("í", "i").replace("é", "e").replace(".", "")
    url = f"https://ar.computrabajo.com/trabajo-de-{slug}{sufijo}"
    if not navegar(page, url, "Computrabajo"):
        return empleos
    try:
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


def extraer_bumeran_zonajobs(page, keyword, dominio, nombre):
    empleos = []
    slug = keyword.lower().replace(" ", "-").replace("í", "i").replace("é", "e").replace(".", "")
    url = f"https://www.{dominio}/empleos-busqueda-{slug}.html"
    if not navegar(page, url, nombre, espera="networkidle"):
        return empleos
    try:
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


def extraer_remoteok(page):
    empleos = []
    if not navegar(page, "https://remoteok.com/api", "RemoteOK"):
        return empleos
    try:
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
# CACHÉ: cargar la corrida anterior
# ═════════════════════════════════════════════
def cargar_anteriores():
    try:
        datos = json.loads(ARCHIVO_SALIDA.read_text(encoding="utf-8"))
        return {e["enlace"]: e for e in datos.get("empleos", []) if e.get("enlace")}
    except Exception:
        return {}


# ═════════════════════════════════════════════
# PROGRAMA PRINCIPAL
# ═════════════════════════════════════════════
def main():
    print("=" * 52)
    print("  EXTRACTOR PERSONALIZADO v3 — iniciando…")
    print("=" * 52)

    anteriores = cargar_anteriores()
    if anteriores:
        print(f"  Caché: {len(anteriores)} ofertas de la corrida anterior.")

    hoy = datetime.now(timezone.utc)
    hoy_str = hoy.date().isoformat()

    todos = []
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        contexto = navegador.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": random.choice([1366, 1440, 1536]), "height": random.choice([768, 864, 900])},
            locale="es-AR",
            timezone_id="America/Argentina/Buenos_Aires",
        )
        # Menos rastro de automatización y menos carga en los servidores:
        contexto.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        contexto.route(re.compile(r"\.(png|jpe?g|gif|webp|svg|woff2?|ttf|mp4)(\?|$)"),
                       lambda ruta: ruta.abort())

        page = contexto.new_page()

        for kw in PALABRAS_CLAVE:
            print(f"\n>> Buscando: '{kw}'")

            r = extraer_linkedin(page, kw, "Misiones, Argentina", solo_remoto=False)
            print(f"   LinkedIn Misiones: {len(r)}")
            todos += r
            pausa_humana()

            r = extraer_linkedin(page, kw, "Argentina", solo_remoto=True)
            print(f"   LinkedIn remoto: {len(r)}")
            todos += r
            pausa_humana()

            r = extraer_computrabajo(page, kw, "-en-misiones")
            print(f"   Computrabajo Misiones: {len(r)}")
            todos += r
            pausa_humana()

            r = extraer_computrabajo(page, kw + " remoto")
            print(f"   Computrabajo remoto: {len(r)}")
            todos += r
            pausa_humana()

            r = extraer_bumeran_zonajobs(page, kw, "bumeran.com.ar", "Bumeran")
            print(f"   Bumeran: {len(r)}")
            todos += r
            pausa_humana()

            r = extraer_bumeran_zonajobs(page, kw, "zonajobs.com.ar", "ZonaJobs")
            print(f"   ZonaJobs: {len(r)}")
            todos += r
            pausa_humana()

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

        # ── Puntuar y filtrar ──
        finales, descartados = [], 0
        for e in unicos:
            resultado = puntuar(e)
            if resultado:
                finales.append(resultado)
            else:
                descartados += 1

        # ── Fusionar con el caché ──
        enlaces_actuales = {e["enlace"] for e in finales}
        reutilizadas, rescatadas = 0, 0
        for e in finales:
            prev = anteriores.get(e["enlace"])
            e["primera_vez"] = prev.get("primera_vez", hoy_str) if prev else hoy_str
            # Si ya teníamos la descripción, la reutilizamos (0 requests extra)
            if prev and prev.get("descripcion") and not e.get("descripcion"):
                aplicar_descripcion(e, prev["descripcion"])
                reutilizadas += 1

        # Ofertas que hoy no aparecieron pero son recientes: las conservamos
        limite = (hoy - timedelta(days=DIAS_RETENER_OFERTA)).date().isoformat()
        for enlace, prev in anteriores.items():
            if enlace not in enlaces_actuales and prev.get("primera_vez", "") >= limite:
                finales.append(prev)
                rescatadas += 1

        if reutilizadas or rescatadas:
            print(f"\n  Caché: {reutilizadas} descripciones reutilizadas, "
                  f"{rescatadas} ofertas recientes conservadas.")

        finales.sort(key=lambda x: x["afinidad"], reverse=True)

        # ── Descripciones nuevas (solo las que faltan, con tope) ──
        candidatas = [e for e in finales if not e.get("descripcion")
                      and e["fuente"] not in bloqueados][:TOP_CON_DESCRIPCION]
        print(f"\n>> Trayendo descripción de {len(candidatas)} ofertas nuevas…")
        for i, e in enumerate(candidatas, 1):
            enriquecer(page, e)
            pausa_humana(2, 4.5)
            if i % 10 == 0:
                print(f"   {i}/{len(candidatas)}…")

        navegador.close()

    finales.sort(key=lambda x: x["afinidad"], reverse=True)

    salida = {
        "actualizado": hoy.isoformat(),
        "total": len(finales),
        "empleos": finales,
    }
    ARCHIVO_SALIDA.write_text(
        json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n" + "=" * 52)
    print(f"  LISTO: {len(finales)} ofertas para tu perfil")
    print(f"  (descartadas {descartados}: seniors o fuera de zona sin remoto)")
    if bloqueados:
        print(f"  Portales salteados por posible bloqueo: {', '.join(bloqueados)}")
        print("  Es temporal: probá de nuevo mañana.")
    print("=" * 52)


if __name__ == "__main__":
    main()
