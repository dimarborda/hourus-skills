#!/usr/bin/env python3
"""
expres.py
=========
Utilidades determinísticas de la skill diseno-express-de-apps.
Solo usa la biblioteca estándar de Python 3.

SUBCOMANDOS
-----------
  entorno                         Revisa Node >= 20, npm, git, gh, Vercel CLI y
                                  Supabase CLI. Dice cómo instalar lo que falte.
                                  NO instala nada.
  iniciar --proyecto RUTA --nombre "Nombre" [--referente "X"]
                                  Crea RUTA/docs/ con las plantillas 00-05 y un
                                  CLAUDE.md del proyecto. NO sobrescribe archivos
                                  existentes (los reporta como omitidos).
  validar --proyecto RUTA         Revisa docs/: decisiones aprobadas, TODO sin
                                  resolver, IDs de casos únicos, puntos Fibonacci
                                  <= 13, prioridad y estado válidos, cada etapa con
                                  criterio de salida y ficha para cada caso 🟥.
                                  Sale con código 1 si hay errores.
  estado --proyecto RUTA          Avance por etapa según la columna Estado de
                                  docs/05-casos-de-uso.md.

QUÉ NO HACE
-----------
No crea la app, no llama a Supabase ni a Vercel y no juzga la calidad del
contenido: solo verifica la forma de los documentos.
"""
import argparse
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
PLANTILLAS = SKILL_DIR / "assets" / "plantillas"
DOCS = [
    "00-decisiones.md",
    "01-referente-conceptual.md",
    "02-referente-casos-de-uso.md",
    "03-diseno-visual.md",
    "04-conceptual.md",
    "05-casos-de-uso.md",
]
FIBONACCI = {1, 2, 3, 5, 8, 13}
PRIORIDADES = {"🟥", "🟨", "🟩"}
ESTADOS = {"⬜", "🔄", "✅"}
RE_ETAPA = re.compile(r"^##\s+(E\d+)\b.*$", re.M)
RE_FILA_UC = re.compile(r"^\|\s*(UC-[A-Z0-9]{2,5}-\d{2,3})\s*\|(.*)$", re.M)
RE_FICHA = re.compile(r"^###\s+(UC-[A-Z0-9]{2,5}-\d{2,3})\b", re.M)
RE_TODO = re.compile(r"\bTODO\b")


# ---------------------------------------------------------------- entorno
def _version(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return (r.stdout or r.stderr).strip().splitlines()[0] if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None


def cmd_entorno(_args):
    mac = sys.platform == "darwin"
    herramientas = [
        ("node", ["node", "-v"], "brew install node" if mac else "https://nodejs.org (LTS)"),
        ("npm", ["npm", "-v"], "viene con Node"),
        ("git", ["git", "--version"], "xcode-select --install" if mac else "https://git-scm.com"),
        ("gh (GitHub CLI)", ["gh", "--version"], "brew install gh" if mac else "https://cli.github.com"),
        ("vercel", ["vercel", "--version"], "npm i -g vercel"),
        ("supabase", ["supabase", "--version"], "brew install supabase/tap/supabase (o usar npx supabase)"),
    ]
    faltan = 0
    for nombre, cmd, instalar in herramientas:
        v = _version(cmd)
        if nombre == "node" and v:
            mayor = int(re.sub(r"[^\d.]", "", v).split(".")[0] or 0)
            if mayor < 20:
                print(f"⚠️  {nombre}: {v} (se necesita >= 20) → {instalar}")
                faltan += 1
                continue
        if v:
            print(f"✅ {nombre}: {v}")
        elif nombre == "supabase" and _version(["npx", "--version"]):
            print(f"🟨 {nombre}: no instalado; se puede usar con `npx supabase` → opcional: {instalar}")
        else:
            print(f"❌ {nombre}: no encontrado → {instalar}")
            faltan += 1
    print("\nCuentas que necesita el usuario: GitHub, Supabase y Vercel (gratuitas para empezar).")
    return 1 if faltan else 0


# ---------------------------------------------------------------- iniciar
def cmd_iniciar(args):
    raiz = Path(args.proyecto).expanduser().resolve()
    docs = raiz / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    reemplazos = {
        "{{PROYECTO}}": args.nombre,
        "{{REFERENTE}}": args.referente or "Referente (TODO)",
        "{{FECHA}}": date.today().isoformat(),
    }
    destinos = [(PLANTILLAS / d, docs / d) for d in DOCS]
    destinos.append((PLANTILLAS / "CLAUDE.md", raiz / "CLAUDE.md"))
    for origen, destino in destinos:
        if destino.exists():
            print(f"⏭️  omitido (ya existe): {destino}")
            continue
        texto = origen.read_text(encoding="utf-8")
        for k, v in reemplazos.items():
            texto = texto.replace(k, v)
        destino.write_text(texto, encoding="utf-8")
        print(f"✅ creado: {destino}")
    return 0


# ---------------------------------------------------------------- validar
def _celdas(resto):
    return [c.strip() for c in resto.strip().strip("|").split("|")]


def _casos(texto):
    """Devuelve [(etapa, id, prioridad, puntos, estado)] desde las tablas."""
    etapas = [(m.start(), m.group(1)) for m in RE_ETAPA.finditer(texto)]
    casos = []
    for m in RE_FILA_UC.finditer(texto):
        etapa = None
        for pos, nombre in etapas:
            if pos < m.start():
                etapa = nombre
        c = _celdas(m.group(2))
        # columnas: caso | actor | prioridad | puntos | estado
        prioridad = c[2] if len(c) > 2 else ""
        puntos = c[3] if len(c) > 3 else ""
        estado = c[4] if len(c) > 4 else ""
        casos.append((etapa, m.group(1), prioridad, puntos, estado))
    return casos


def cmd_validar(args):
    docs = Path(args.proyecto).expanduser().resolve() / "docs"
    errores, avisos = [], []

    for d in DOCS:
        if not (docs / d).exists():
            errores.append(f"falta docs/{d}")

    dec = docs / "00-decisiones.md"
    if dec.exists():
        t = dec.read_text(encoding="utf-8")
        for n in range(1, 6):
            m = re.search(rf"^##\s+D{n}\b(.*?)(?=^##\s+D\d|\Z)", t, re.M | re.S)
            if not m:
                errores.append(f"00-decisiones: falta la sección D{n}")
                continue
            bloque = m.group(1)
            if not re.search(r"\*\*Estado:\*\*\s*aprobada", bloque, re.I):
                errores.append(f"00-decisiones: D{n} no está aprobada")
            if RE_TODO.search(bloque):
                errores.append(f"00-decisiones: D{n} tiene TODO sin resolver")

    for d in DOCS[1:]:
        p = docs / d
        if p.exists():
            n = len(RE_TODO.findall(p.read_text(encoding="utf-8")))
            if n:
                avisos.append(f"{d}: {n} TODO sin resolver")

    cu = docs / "05-casos-de-uso.md"
    if cu.exists():
        t = cu.read_text(encoding="utf-8")
        etapas = [m.group(1) for m in RE_ETAPA.finditer(t)]
        if "E0" not in etapas:
            errores.append("05-casos-de-uso: falta la etapa E0 (cimientos)")
        if "E1" not in etapas:
            errores.append("05-casos-de-uso: falta la etapa E1 (MVP)")
        for m in RE_ETAPA.finditer(t):
            fin = t.find("\n## ", m.end())
            bloque = t[m.end(): fin if fin != -1 else len(t)]
            if "Criterio de salida:" not in bloque:
                errores.append(f"05-casos-de-uso: {m.group(1)} sin '**Criterio de salida:**'")
        casos = _casos(t)
        if not casos:
            errores.append("05-casos-de-uso: no hay filas de casos (| UC-XXX-nn | … |)")
        vistos = {}
        fichas = set(RE_FICHA.findall(t))
        for etapa, uid, prio, pts, est in casos:
            if uid in vistos:
                errores.append(f"{uid}: ID repetido")
            vistos[uid] = etapa
            if etapa is None:
                errores.append(f"{uid}: está fuera de una sección '## E<n>'")
            if prio not in PRIORIDADES:
                errores.append(f"{uid}: prioridad '{prio}' no es 🟥/🟨/🟩")
            if not pts.isdigit() or int(pts) not in FIBONACCI:
                errores.append(f"{uid}: puntos '{pts}' no son Fibonacci 1-13 (si da 21, descomponer)")
            if est not in ESTADOS:
                errores.append(f"{uid}: estado '{est}' no es ⬜/🔄/✅")
            if prio == "🟥" and uid not in fichas:
                avisos.append(f"{uid}: es 🟥 y no tiene ficha '### {uid} · …'")

    for e in errores:
        print(f"❌ {e}")
    for a in avisos:
        print(f"⚠️  {a}")
    if not errores and not avisos:
        print("✅ Documentos completos y consistentes.")
    elif not errores:
        print("✅ Sin errores (revisa los avisos).")
    return 1 if errores else 0


# ---------------------------------------------------------------- estado
def cmd_estado(args):
    raiz = Path(args.proyecto).expanduser().resolve()
    docs = raiz / "docs"
    print(f"Proyecto: {raiz}")
    for d in DOCS:
        p = docs / d
        if not p.exists():
            print(f"  ❌ {d}")
            continue
        n = len(RE_TODO.findall(p.read_text(encoding="utf-8")))
        print(f"  {'✅' if n == 0 else '📝'} {d}" + (f" ({n} TODO)" if n else ""))
    cu = docs / "05-casos-de-uso.md"
    if not cu.exists():
        return 0
    t = cu.read_text(encoding="utf-8")
    nombres = {m.group(1): m.group(0).lstrip("# ").strip() for m in RE_ETAPA.finditer(t)}
    resumen = {}
    for etapa, _uid, _p, pts, est in _casos(t):
        r = resumen.setdefault(etapa, {"⬜": 0, "🔄": 0, "✅": 0, "pts": 0, "pts_ok": 0})
        if est in ESTADOS:
            r[est] += 1
        p = int(pts) if pts.isdigit() else 0
        r["pts"] += p
        if est == "✅":
            r["pts_ok"] += p
    print("\nAvance por etapa:")
    actual = None
    for etapa, r in resumen.items():
        total = r["⬜"] + r["🔄"] + r["✅"]
        pct = round(100 * r["pts_ok"] / r["pts"]) if r["pts"] else 0
        print(f"  {nombres.get(etapa, etapa)}: {r['✅']}/{total} casos ✅, "
              f"{r['🔄']} en curso · {r['pts_ok']}/{r['pts']} puntos ({pct} %)")
        if actual is None and r["✅"] < total:
            actual = etapa
    if actual:
        print(f"\nEtapa en curso: {nombres.get(actual, actual)}")
    elif resumen:
        print("\nTodas las etapas definidas están terminadas.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Utilidades de la skill diseno-express-de-apps.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("entorno", help="revisar herramientas instaladas")
    p = sub.add_parser("iniciar", help="crear docs/ y CLAUDE.md desde plantillas")
    p.add_argument("--proyecto", required=True)
    p.add_argument("--nombre", required=True)
    p.add_argument("--referente")
    for nombre in ("validar", "estado"):
        p = sub.add_parser(nombre)
        p.add_argument("--proyecto", required=True)
    args = ap.parse_args()
    return {"entorno": cmd_entorno, "iniciar": cmd_iniciar,
            "validar": cmd_validar, "estado": cmd_estado}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
