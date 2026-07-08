"""
=============================================================
 AUTOMATIZADOR (deploy.py)
=============================================================
 1. Ejecuta extractor.py  → genera empleos.json actualizado
 2. Hace git add + commit + push → Cloudflare Pages / Netlify
    detecta el cambio y actualiza la web sola.

 Cómo ejecutarlo:  python deploy.py
=============================================================
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

CARPETA = Path(__file__).parent  # trabajamos siempre en la carpeta del proyecto


def correr(comando, descripcion):
    """Ejecuta un comando y corta el programa si falla."""
    print(f"\n>> {descripcion}")
    resultado = subprocess.run(comando, cwd=CARPETA, capture_output=True, text=True)
    if resultado.stdout:
        print(resultado.stdout.strip())
    if resultado.returncode != 0:
        print(f"[ERROR] {resultado.stderr.strip()}")
        return False
    return True


def main():
    # ── PASO 1: extraer las ofertas ──
    if not correr([sys.executable, "extractor.py"], "Ejecutando extractor.py…"):
        sys.exit("El extractor falló. No se subió nada.")

    # ── PASO 2: verificar si hay cambios reales ──
    estado = subprocess.run(
        ["git", "status", "--porcelain", "empleos.json"],
        cwd=CARPETA, capture_output=True, text=True,
    )
    if not estado.stdout.strip():
        print("\nNo hay ofertas nuevas. Nada que subir. ✔")
        return

    # ── PASO 3: subir a GitHub ──
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    correr(["git", "add", "empleos.json"], "git add empleos.json")
    correr(["git", "commit", "-m", f"Auto-update jobs {fecha}"], "git commit")
    # Por si el robot de GitHub subió algo mientras tanto, primero traemos lo nuevo.
    # Si hay conflicto en empleos.json, gana NUESTRA versión (la recién generada).
    if not correr(["git", "pull", "--rebase", "origin", "main"], "git pull (sincronizando…)"):
        print(">> Conflicto detectado: nos quedamos con los datos recién extraídos.")
        correr(["git", "checkout", "--theirs", "empleos.json"], "resolviendo conflicto")
        correr(["git", "add", "empleos.json"], "git add")
        correr(["git", "-c", "core.editor=true", "rebase", "--continue"], "continuando…")
    if correr(["git", "push"], "git push (subiendo a GitHub…)"):
        print("\n✔ LISTO: la web se actualizará sola en 1-2 minutos.")


if __name__ == "__main__":
    main()
