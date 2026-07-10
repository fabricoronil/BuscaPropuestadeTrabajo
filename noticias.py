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
import sys
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree

# En la consola de Windows (cp1252) los emojis y flechas de los mensajes
# rompen con UnicodeEncodeError. Forzamos UTF-8 para poder correrlo local.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ARCHIVO_SALIDA = Path(__file__).parent / "noticias.json"
MAX_POR_CATEGORIA = 14
MAX_TRADUCCIONES = 220   # tope de traducciones NUEVAS por corrida (con caché, en régimen son pocas)

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
# Cada consulta puede ser un string (se busca en Google News Argentina/español)
# o una tupla (texto, "US") para buscar en Google News global/inglés —
# clave para los lanzamientos de IA que primero salen en medios en inglés.
CATEGORIAS = {
    "Silicon Misiones": [
        '"Silicon Misiones"',
        '"Polo TIC" Misiones',
    ],
    "Misiones y Posadas IT": [
        'Misiones "desarrollo de software" OR programadores OR "polo tecnológico"',
        'Posadas OR Misiones "economía del conocimiento" OR "empresa de software" OR "startup tecnológica"',
        'Misiones "inteligencia artificial" OR "innovación tecnológica" OR robótica',
        'Posadas OR Misiones "Silicon Misiones" OR "Parque Industrial" tecnología OR software',
    ],
    "Inteligencia Artificial": [
        "inteligencia artificial",
        "OpenAI OR ChatGPT OR GPT-5 OR GPT-6",
        '"Claude" OR "Claude AI" OR Anthropic inteligencia artificial',
        "Claude OR Anthropic OR Gemini OR Google DeepMind",
        "Llama OR Meta AI OR Mistral OR DeepSeek OR Grok OR Copilot",
        "nuevo modelo de inteligencia artificial lanzamiento",
        "IA generativa OR modelo de lenguaje OR agentes de IA",
        "Nvidia OR chips IA OR GPU inteligencia artificial",
        # Global / inglés: lo primero que aparece cuando hay un lanzamiento grande
        ("OpenAI OR ChatGPT OR GPT-5 OR GPT-6 new model", "US"),
        ("Anthropic Claude OR Google Gemini OR Meta Llama release", "US"),
        ("new AI model launch OR announcement", "US"),
        ("artificial intelligence breakthrough", "US"),
    ],
    "Herramientas para Programadores": [
        "GitHub Copilot OR Cursor OR programar con inteligencia artificial",
        "asistente de código IA OR autocompletado de código",
        ("AI coding assistant OR Cursor OR GitHub Copilot OR Claude Code", "US"),
    ],
    "Cursos y Becas": [
        "curso gratis OR beca Google OR Meta programación OR inteligencia artificial",
        "becas IA Google Argentina OR certificación desarrollo web",
        "Google Actívate OR Meta Blueprint OR digitalers curso gratis programación",
        "cursos gratuitos programación OR tecnología Argentina",
    ],
    "Desarrollo de Software": [
        "desarrollo de software",
        "JavaScript OR TypeScript OR React OR Node.js novedad",
        ("React OR Node.js OR TypeScript OR Next.js release", "US"),
    ],
    "Empresas Tech": [
        "Google OR Meta OR Microsoft OR Apple OR Amazon tecnología",
        "Nvidia OR Tesla OR startups tecnología inversión",
    ],
    "Despidos y Contrataciones": [
        "despidos tecnología OR tecnológicas",
        "contrataciones OR búsqueda programadores OR desarrolladores Argentina",
        ("tech layoffs OR tech hiring", "US"),
    ],
    "Voces del Sector": [
        "Sam Altman OR Elon Musk OR Mark Zuckerberg OR Satya Nadella OR Sundar Pichai dijo OR opinión OR advirtió",
        "Bill Gates OR Jensen Huang OR Demis Hassabis inteligencia artificial futuro",
    ],
    "Empleo IT": [
        "empleo IT Argentina",
        "trabajo remoto tecnología Argentina",
    ],
}

# ═════════════════════════════════════════════
# FUENTE 3: feeds directos de medios tech
# ═════════════════════════════════════════════
# Cada feed: (categoría, url, idioma). El idioma marca si hay que traducir al español.
FEEDS_DIRECTOS = [
    # ── FUENTES OFICIALES DE IA (acá se anuncian los lanzamientos primero) ──
    ("Inteligencia Artificial", "https://openai.com/news/rss.xml", "en"),           # OpenAI oficial
    ("Inteligencia Artificial", "https://deepmind.google/blog/rss.xml", "en"),      # Google DeepMind oficial
    ("Inteligencia Artificial", "https://blog.google/technology/ai/rss/", "en"),    # Google AI oficial
    ("Inteligencia Artificial", "https://huggingface.co/blog/feed.xml", "en"),      # Hugging Face oficial
    ("Inteligencia Artificial", "https://blogs.nvidia.com/feed/", "en"),            # NVIDIA oficial
    ("Inteligencia Artificial", "https://aws.amazon.com/blogs/machine-learning/feed/", "en"),  # AWS ML oficial

    # ── IA: medios internacionales especializados ──
    ("Inteligencia Artificial", "https://techcrunch.com/category/artificial-intelligence/feed/", "en"),
    ("Inteligencia Artificial", "https://venturebeat.com/category/ai/feed/", "en"),
    ("Inteligencia Artificial", "https://www.technologyreview.com/topic/artificial-intelligence/feed/", "en"),
    ("Inteligencia Artificial", "https://the-decoder.com/feed/", "en"),
    ("Inteligencia Artificial", "https://simonwillison.net/atom/everything/", "en"),

    # ── Medios tech grandes en español ──
    ("Tecnología Global", "https://www.xataka.com/index.xml", "es"),
    ("Tecnología Global", "https://www.genbeta.com/index.xml", "es"),
    ("Tecnología Global", "https://hipertextual.com/feed", "es"),
    ("Tecnología Global", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/tecnologia/portada", "es"),
    ("Tecnología Global", "https://www.infobae.com/arc/outboundfeeds/rss/category/tecno/?outputType=xml", "es"),

    # ── Medios tech grandes internacionales ──
    ("Tecnología Global", "https://techcrunch.com/feed/", "en"),
    ("Tecnología Global", "https://www.theverge.com/rss/index.xml", "en"),
    ("Tecnología Global", "https://feeds.arstechnica.com/arstechnica/technology-lab", "en"),
    ("Tecnología Global", "https://www.wired.com/feed/rss", "en"),
    ("Tecnología Global", "https://www.engadget.com/rss.xml", "en"),
    ("Tecnología Global", "https://feeds.bbci.co.uk/news/technology/rss.xml", "en"),
    ("Tecnología Global", "https://www.theguardian.com/technology/rss", "en"),
    ("Tecnología Global", "https://spectrum.ieee.org/feeds/feed.rss", "en"),

    # ── Comunidad de desarrolladores (blogs de referencia + lo que se discute hoy) ──
    ("Comunidad Dev", "https://github.blog/feed/", "en"),                 # GitHub oficial
    ("Comunidad Dev", "https://stackoverflow.blog/feed/", "en"),          # Stack Overflow oficial
    ("Comunidad Dev", "https://dev.to/feed", "en"),
    ("Comunidad Dev", "https://www.reddit.com/r/devsarg/.rss", "es"),     # devs argentinos
    ("Comunidad Dev", "https://hnrss.org/frontpage", "en"),               # Hacker News (portada)
    ("Inteligencia Artificial", "https://www.reddit.com/r/OpenAI/.rss", "en"),
    ("Inteligencia Artificial", "https://www.reddit.com/r/LocalLLaMA/.rss", "en"),
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
        resumen = limpiar_html(item.findtext("description", ""))[:500]
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
                               or entrada.findtext(ATOM + "content", ""))[:500]
        fecha = (entrada.findtext(ATOM + "updated", "")
                 or entrada.findtext(ATOM + "published", ""))[:10]
        if titulo and enlace:
            items.append({"titulo": titulo, "enlace": enlace, "fuente": "",
                          "fecha": fecha, "resumen": resumen})
    return items


def traducir(texto):
    """Traduce inglés → español con el endpoint gratuito de Google Translate."""
    if not texto or not texto.strip():
        return ""
    url = ("https://translate.googleapis.com/translate_a/single"
           "?client=gtx&sl=en&tl=es&dt=t&q=" + quote(texto))
    data = json.loads(descargar(url).decode("utf-8", errors="ignore"))
    return "".join(seg[0] for seg in data[0] if seg and seg[0])


def cargar_traducciones_anteriores():
    """Traducciones ya hechas en corridas previas (título → item), para no repetirlas."""
    try:
        datos = json.loads(ARCHIVO_SALIDA.read_text(encoding="utf-8"))
        return {n["titulo"]: n for n in datos.get("noticias", []) if n.get("titulo_es")}
    except Exception:
        return {}


def buscar_google_news(consulta, region="AR"):
    if region == "US":
        url = ("https://news.google.com/rss/search?"
               f"q={quote(consulta)}&hl=en-US&gl=US&ceid=US:en")
    else:
        url = ("https://news.google.com/rss/search?"
               f"q={quote(consulta)}&hl=es-419&gl=AR&ceid=AR:es-419")
    return parsear_feed(descargar(url))


def normalizar_consulta(consulta):
    """Acepta 'texto' o ('texto', 'US') y devuelve (texto, region)."""
    if isinstance(consulta, tuple):
        return consulta[0], consulta[1]
    return consulta, "AR"


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
            n.setdefault("idioma", "es")
            noticias.append(n)
            agregadas += 1
        return agregadas

    # ── 1. Silicon Misiones: sitio oficial + Google News ──
    print("\n>> Silicon Misiones (sitio oficial)…")
    encontradas = noticias_silicon_directo()
    for consulta in CATEGORIAS["Silicon Misiones"]:
        texto, region = normalizar_consulta(consulta)
        try:
            res = buscar_google_news(texto, region)
            for it in res:
                it["idioma"] = "en" if region == "US" else "es"
            encontradas += res
        except Exception as ex:
            print(f"  [!] Falló '{texto}': {type(ex).__name__}")
    n = agregar(encontradas, "Silicon Misiones", tope=18)
    print(f"  → Silicon Misiones: {n} noticias en total")

    # ── 2. Resto de categorías por Google News ──
    for categoria, consultas in CATEGORIAS.items():
        if categoria == "Silicon Misiones":
            continue
        encontradas = []
        for consulta in consultas:
            texto, region = normalizar_consulta(consulta)
            try:
                res = buscar_google_news(texto, region)
                for it in res:
                    it["idioma"] = "en" if region == "US" else "es"
                encontradas += res
            except Exception as ex:
                print(f"  [!] Falló '{texto}': {type(ex).__name__}")
        tope = 22 if categoria == "Inteligencia Artificial" else MAX_POR_CATEGORIA
        n = agregar(encontradas, categoria, tope=tope)
        print(f"  {categoria}: {n} noticias")

    # ── 3. Medios tech directos ──
    for categoria, feed, idioma in FEEDS_DIRECTOS:
        try:
            items = parsear_feed(descargar(feed))
            for i in items:
                i["fuente"] = i["fuente"] or feed.split("/")[2].replace("www.", "")
                i["idioma"] = idioma
            n = agregar(items, categoria, tope=8)
            print(f"  {feed.split('/')[2]}: {n} noticias")
        except Exception as ex:
            print(f"  [!] Falló el feed {feed}: {type(ex).__name__}")

    # ── 4. Traducir al español las noticias en inglés (reutilizando la caché) ──
    print("\n>> Traduciendo noticias en inglés…")
    cache_tr = cargar_traducciones_anteriores()
    nuevas_trad = reutilizadas = 0
    for n in noticias:
        if n.get("idioma") != "en":
            continue
        previa = cache_tr.get(n["titulo"])
        if previa and previa.get("titulo_es"):
            n["titulo_es"] = previa.get("titulo_es", "")
            n["resumen_es"] = previa.get("resumen_es", "")
            reutilizadas += 1
        elif nuevas_trad < MAX_TRADUCCIONES:
            try:
                n["titulo_es"] = traducir(n["titulo"])
                n["resumen_es"] = traducir(n["resumen"]) if n.get("resumen") else ""
                nuevas_trad += 1
            except Exception as ex:
                print(f"  [!] No se pudo traducir una noticia: {type(ex).__name__}")
    print(f"  Traducciones: {nuevas_trad} nuevas · {reutilizadas} reutilizadas de la caché")

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
