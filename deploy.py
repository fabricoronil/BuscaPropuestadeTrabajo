"""
=============================================================
 AUTOMATIZADOR (deploy.py)  v2 — a prueba de conflictos
=============================================================
 1. Ejecuta extractor.py → genera empleos.json actualizado
 2. Sube el resultado a GitHub.

 Regla de oro: empleos.json se regenera completo cada vez,
 así que NUNCA se fusionan versiones. Si tu PC y el robot
 de GitHub chocan, gana la versión más nueva (la tuya) de
 forma automática. Sin conflictos, sin JSON roto.

 Cómo ejecutarlo:  python deploy.py
=============================================================
"""

import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

CARPETA = Path(__file__).parent
ARCHIVOS_DATOS = ["empleos.json", "noticias.json"]  # lo que sube este script


def correr(comando, descripcion, mostrar_error=True):
    print(f"\n>> {descripcion}")
    r = subprocess.run(comando, cwd=CARPETA, capture_output=True, text=True)
    if r.stdout.strip():
        print(r.stdout.strip())
    if r.returncode != 0 and mostrar_error:
        print(f"[aviso] {r.stderr.strip()[:300]}")
    return r.returncode == 0


def hay_cambios():
    r = subprocess.run(["git", "status", "--porcelain"] + ARCHIVOS_DATOS,
                       cwd=CARPETA, capture_output=True, text=True)
    return bool(r.stdout.strip())


def subir():
    """Intenta subir con rebase automático. Si algo sale mal,
    plan B: se alinea con GitHub y reaplica los datos nuevos encima."""
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")

    correr(["git", "add"] + ARCHIVOS_DATOS, "git add (empleos + noticias)")
    correr(["git", "commit", "-m", f"Auto-update datos {fecha}"], "git commit")

    for intento in (1, 2, 3):
        # -X theirs: si hay conflicto en el rebase, ganan NUESTROS datos nuevos
        # --autostash: no molesta si tenés otros archivos editados sin commitear
        sincronizado = correr(
            ["git", "pull", "--rebase", "--autostash", "-X", "theirs", "origin", "main"],
            f"Sincronizando con GitHub (intento {intento})…",
        )
        if sincronizado and correr(["git", "push"], "git push"):
            print("\n✔ LISTO: la web se actualizará sola en 1-2 minutos.")
            return True
        # Si el rebase quedó a medias, lo cancelamos antes de reintentar
        correr(["git", "rebase", "--abort"], "limpiando…", mostrar_error=False)
        time.sleep(3)

    # ── PLAN B (no puede fallar): igualarse a GitHub y poner los datos encima ──
    print("\n>> Plan B: alineando con GitHub y reaplicando los datos nuevos…")
    respaldos = {}
    for nombre in ARCHIVOS_DATOS:                     # 1. guardamos los datos nuevos
        origen = CARPETA / nombre
        if origen.exists():
            respaldos[nombre] = origen.read_bytes()
    correr(["git", "fetch", "origin"], "git fetch")
    correr(["git", "reset", "--hard", "origin/main"], "alineando con GitHub")
    for nombre, contenido in respaldos.items():       # 2. los volvemos a poner
        (CARPETA / nombre).write_bytes(contenido)
    correr(["git", "add"] + ARCHIVOS_DATOS, "git add")
    correr(["git", "commit", "-m", f"Auto-update datos {fecha}"], "git commit")
    if correr(["git", "push"], "git push"):
        print("\n✔ LISTO (vía plan B): la web se actualizará en 1-2 minutos.")
        return True
    print("\n[ERROR] No se pudo subir. ¿Hay internet? Probá de nuevo en unos minutos.")
    return False


def main():
    # ── PASO 1: extraer ──
    # (sin capturar la salida: así ves el progreso del extractor en vivo)
    print("\n>> Ejecutando extractor.py… (tarda 10-15 min, vas a ver el avance acá)")
    r = subprocess.run([sys.executable, "-u", "extractor.py"], cwd=CARPETA)
    if r.returncode != 0:
        sys.exit("El extractor falló. No se subió nada.")

    # ── PASO 1b: noticias (si falla, no frena el resto) ──
    print("\n>> Buscando noticias IT…")
    subprocess.run([sys.executable, "-u", "noticias.py"], cwd=CARPETA)

    # ── PASO 2: ¿hay algo nuevo? ──
    if not hay_cambios():
        print("\nNo hay ofertas nuevas. Nada que subir. ✔")
        return

    # ── PASO 3: subir ──
    subir()


if __name__ == "__main__":
    main()
