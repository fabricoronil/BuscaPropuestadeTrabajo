"""
=============================================================
 BUSCADOR DE NOTICIAS IT (noticias.py)  v2
=============================================================
 Junta noticias de tu área desde varias fuentes gratuitas:

 1. SITIO OFICIAL de Silicon Misiones (lee su feed y, si no
    responde, la página directamente) → cursos, eventos, todo.
 2. Google News (RSS gratis) con búsquedas por categoría:
    Misiones/Posadas IT, IA, software, despidos y
    contrataciones, y declaraciones de referentes del sector.
 3. Feeds directos de medios tech (TechCrunch, Xataka).

 Detecta cuáles noticias son NUEVAS respecto a la corrida
 anterior y las marca para que la web les ponga el badge ✨.

 Cómo ejecutarlo:  python noticias.py
 (deploy.py y el robot de las 7:00 lo ejecutan solos)
=============================================================
"""

import json
import re
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree

ARCHIVO_SALIDA = Path(__file__).parent / "noticias.json"
MAX_POR_CATEGORIA = 14

# ═════════════════════════════════════════════
# FUENTE 1: Silicon Misiones (sitio oficial)
# ═════════════════════════════════════════════
SILICON_FEEDS = [
    "https://siliconmisiones.gob.ar/feed/",
    "https://siliconmisiones.gob.ar/noticias/feed/",
]
SILICON_HOME = "https://siliconmisiones.gob.ar/"

# ═════════════════════════════════════════════
# FUENTE 2: búsquedas en Google News por categoría
# ═════════════════════════════════════════════
CATEGORIAS = {
    "Silicon Misiones": [
        '"Silicon Misiones"',
        '"Polo TIC" Misiones',
    ],
    "Misiones y Posadas IT": [
        "Misiones tecnología OR software OR programación OR informática",
        'Posadas OR Misiones "sistemas" universidad OR carrera OR curso OR capacitación',
    ],
    "Inteligencia Artificial": [
        "inteligencia artificial",
        "OpenAI OR ChatGPT OR Claude OR Gemini OR Anthropic",
    ],
    "Desarrollo de Software": [
        "desarrollo de software",
        "programación JavaScript OR React OR Node.js",
    ],
    "Empresas Tech": [
        "Google OR Meta OR Microsoft OR Apple OR Amazon tecnología",
    ],
    "Despidos y Contrataciones": [
        "despidos tecnología OR tecnológicas",
        "contrataciones OR búsqueda programadores OR desarrolladores Argentina",
        "tech layoffs",
    ],
    "Voces del Sector": [
        "Sam Altman OR Elon Musk OR Mark Zuckerberg OR Satya Nadella OR Sundar Pichai dijo OR opinión OR advirtió",
        "Bill Gates OR Jensen Huang inteligencia artificial futuro",
    ],
    "Empleo IT": [
        "empleo IT Argentina",
        "trabajo remoto tecnología Argentina",
    ],
}

# ═════════════════════════════════════════════
# FUENTE 3: feeds directos de medios tech
# ═════════════════════════════════════════════
FEEDS_DIRECTOS = [
    ("Tecnología Global", "https://techcrunch.com/feed/"),
    ("Tecnología Global", "https://www.xataka.com/index.xml"),
    # Comunidad: lo que discuten los desarrolladores ahora mismo
    ("Comunidad Dev", "https://www.reddit.com/r/devsarg/.rss"),          # devs argentinos
    ("Comunidad Dev", "https://hnrss.org/frontpage"),                     # Hacker News (portada)
    ("Inteligencia Artificial", "https://www.reddit.com/r/artificial/.rss"),
]

CABECERAS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
ATOM = "{http://www.w3.org/2005/Atom}"


def limpiar_html(texto):
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    return re.sub(r"\s+", " ", texto).strip()


def descargar(url):
    peticion = urllib.request.Request(url, headers=CABECERAS)
    with urllib.request.urlopen(peticion, timeout=20) as r:
        return r.read()


def parsear_feed(crudo):
    """Lee un feed RSS o Atom y devuelve las noticias."""
    arbol = ElementTree.fromstring(crudo)
    items = []

    # Formato RSS (<item>)
    for item in arbol.iter("item"):
        titulo = limpiar_html(item.findtext("title", ""))
        enlace = (item.findtext("link", "") or "").strip()
        fuente = limpiar_html(item.findtext("source", ""))
        resumen = limpiar_html(item.findtext("description", ""))[:250]
        fecha = ""
        try:
            fecha = parsedate_to_datetime(item.findtext("pubDate", "")).date().isoformat()
        except Exception:
            pass
        if titulo and enlace:
            items.append({"titulo": titulo, "enlace": enlace, "fuente": fuente,
                          "fecha": fecha, "resumen": resumen})

    # Formato Atom (<entry>)
    for entrada in arbol.iter(ATOM + "entry"):
        titulo = limpiar_html(entrada.findtext(ATOM + "title", ""))
        enlace = ""
        link_el = entrada.find(ATOM + "link")
        if link_el is not None:
            enlace = (link_el.get("href") or "").strip()
        resumen = limpiar_html(entrada.findtext(ATOM + "summary", "")
                               or entrada.findtext(ATOM + "content", ""))[:250]
        fecha = (entrada.findtext(ATOM + "updated", "")
                 or entrada.findtext(ATOM + "published", ""))[:10]
        if titulo and enlace:
            items.append({"titulo": titulo, "enlace": enlace, "fuente": "",
                          "fecha": fecha, "resumen": resumen})
    return items


def buscar_google_news(consulta):
    url = ("https://news.google.com/rss/search?"
           f"q={quote(consulta)}&hl=es-419&gl=AR&ceid=AR:es-419")
    return parsear_feed(descargar(url))


def noticias_silicon_directo():
    """Lee el sitio oficial de Silicon Misiones: primero su feed,
    y si no anda, saca los títulos de la portada."""
    # Intento 1: feeds de WordPress
    for feed in SILICON_FEEDS:
        try:
            items = parsear_feed(descargar(feed))
            if items:
                for n in items:
                    n["fuente"] = n["fuente"] or "Silicon Misiones (oficial)"
                print(f"  Silicon oficial: {len(items)} publicaciones desde su feed.")
                return items
        except Exception:
            continue

    # Intento 2: leer los links de la portada
    try:
        html = descargar(SILICON_HOME).decode("utf-8", errors="ignore")
        vistos, items = set(), []
        for m in re.finditer(r'<a[^>]+href="(https?://siliconmisiones\.gob\.ar/[^"]+)"[^>]*>(.*?)</a>', html, re.S):
            enlace, texto = m.group(1).split("#")[0], limpiar_html(m.group(2))
            if len(texto) < 25 or enlace in vistos:
                continue
            vistos.add(enlace)
            items.append({"titulo": texto[:140], "enlace": enlace,
                          "fuente": "Silicon Misiones (oficial)", "fecha": "", "resumen": ""})
            if len(items) >= 10:
                break
        print(f"  Silicon oficial: {len(items)} publicaciones desde la portada.")
        return items
    except Exception as ex:
        print(f"  [!] No se pudo leer el sitio de Silicon Misiones: {type(ex).__name__}")
        return []


def cargar_titulos_anteriores():
    """Títulos de la corrida anterior, para detectar cuáles son NUEVAS."""
    try:
        datos = json.loads(ARCHIVO_SALIDA.read_text(encoding="utf-8"))
        return {n["titulo"].lower()[:80] for n in datos.get("noticias", [])}
    except Exception:
        return set()


def main():
    print("=" * 52)
    print("  NOTICIAS IT v2 — buscando en todas las fuentes…")
    print("=" * 52)

    anteriores = cargar_titulos_anteriores()
    noticias, titulos_vistos = [], set()

    def agregar(items, categoria, tope=MAX_POR_CATEGORIA):
        agregadas = 0
        items.sort(key=lambda n: n["fecha"], reverse=True)
        for n in items:
            clave = n["titulo"].lower()[:80]
            if clave in titulos_vistos or agregadas >= tope:
                continue
            titulos_vistos.add(clave)
            n["categoria"] = categoria
            n["nueva"] = bool(anteriores) and clave not in anteriores
            noticias.append(n)
            agregadas += 1
        return agregadas

    # ── 1. Silicon Misiones: sitio oficial + Google News ──
    print("\n>> Silicon Misiones (sitio oficial)…")
    encontradas = noticias_silicon_directo()
    for consulta in CATEGORIAS["Silicon Misiones"]:
        try:
            encontradas += buscar_google_news(consulta)
        except Exception as ex:
            print(f"  [!] Falló '{consulta}': {type(ex).__name__}")
    n = agregar(encontradas, "Silicon Misiones", tope=18)
    print(f"  → Silicon Misiones: {n} noticias en total")

    # ── 2. Resto de categorías por Google News ──
    for categoria, consultas in CATEGORIAS.items():
        if categoria == "Silicon Misiones":
            continue
        encontradas = []
        for consulta in consultas:
            try:
                encontradas += buscar_google_news(consulta)
            except Exception as ex:
                print(f"  [!] Falló '{consulta}': {type(ex).__name__}")
        n = agregar(encontradas, categoria)
        print(f"  {categoria}: {n} noticias")

    # ── 3. Medios tech directos ──
    for categoria, feed in FEEDS_DIRECTOS:
        try:
            items = parsear_feed(descargar(feed))
            for i in items:
                i["fuente"] = i["fuente"] or feed.split("/")[2].replace("www.", "")
            n = agregar(items, categoria, tope=8)
            print(f"  {feed.split('/')[2]}: {n} noticias")
        except Exception as ex:
            print(f"  [!] Falló el feed {feed}: {type(ex).__name__}")

    nuevas = sum(1 for x in noticias if x.get("nueva"))
    salida = {
        "actualizado": datetime.now(timezone.utc).isoformat(),
        "total": len(noticias),
        "nuevas": nuevas,
        "noticias": noticias,
    }
    ARCHIVO_SALIDA.write_text(
        json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n  LISTO: {len(noticias)} noticias ({nuevas} nuevas desde la última corrida)")


if __name__ == "__main__":
    main()
