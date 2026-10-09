#!/usr/bin/env python3
"""
diagnosticar_pdf.py
====================
Inspecciona uno o varios PDF ANTES de convertirlos y recomienda la ruta de
conversión de esta skill. No escribe nada: solo lee y reporta.

Por qué existe: en los casos reales que motivaron esta skill, la mayor
parte del tiempo perdido vino de mandar un PDF por la ruta equivocada
(un escaneo al motor normativo, una guía a columnas al motor de artículos,
una tabla real tratada como columnas de prosa). Este script hace ese
triaje en segundos.

Señales que mide (con pdfplumber):
  - Caracteres de texto por página      -> ¿escaneado? (necesita OCR)
  - Marcadores "ARTÍCULO N"             -> ¿norma articulada? (motor normativo)
  - Tabla de contenido / marcadores     -> ¿guía/manual por secciones?
  - Líneas partidas por un hueco ancho  -> ¿diseño a columnas?
  - Ancho de página > 800 pt            -> ¿pliego horizontal doble?
  - page.find_tables()                  -> ¿tablas con grilla real?
  - Artefactos "(cid:N)"                -> ¿ecuaciones/símbolos rotos?
  - "deteccion" de los perfiles de fuente -> ¿conviene --perfil-fuente?
    (perfiles-fuente/*.json del directorio de trabajo y de PDF_MD_PERFILES)

USO
---
    python3 diagnosticar_pdf.py archivo.pdf [otro.pdf ...]
    python3 diagnosticar_pdf.py carpeta/            # todos los .pdf
    python3 diagnosticar_pdf.py archivo.pdf --json  # salida máquina

Requisitos: pip install pdfplumber
"""

import glob
import logging
import json
import os
import re
import sys

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    print("Falta pdfplumber: pip install pdfplumber")
    sys.exit(2)

MAX_PAGINAS_MUESTRA = 40        # páginas analizadas en documentos largos
MIN_CHARS_PAGINA_CON_TEXTO = 80 # por debajo, la página se considera "sin texto"
HUECO_COLUMNA_PT = 14           # mismo umbral que guias_tecnicas.py
ANCHO_PLIEGO_PT = 800           # mismo umbral que guias_tecnicas.py

ARTICULO_RE = re.compile(
    r"^\s*ART[ÍI]CULO\s+(?:\d+|[ÚU]NICO|PRIMERO|SEGUNDO|TERCERO)", re.IGNORECASE | re.MULTILINE
)
TOC_RE = re.compile(
    r"^\s*(?:TABLA\s+DE\s+)?(?:CONTENIDO|[ÍI]NDICE)\s*(?:GENERAL)?\s*$", re.IGNORECASE | re.MULTILINE
)
TOC_ENTRY_RE = re.compile(r"(?:\.\s?){3,}\s*\d+\s*$", re.MULTILINE)
CID_RE = re.compile(r"\(cid:\d+\)")
# Dónde buscar perfiles de fuente: "perfiles-fuente/" en el directorio de
# trabajo (cwd o PDF_MD_WORKDIR) y las carpetas extra de PDF_MD_PERFILES
# (separadas por ":"). La skill no trae perfiles: son propios de cada lote.
DIRS_PERFILES_FUENTE = [
    os.path.join(os.path.abspath(os.environ.get("PDF_MD_WORKDIR", os.getcwd())), "perfiles-fuente")
] + [d for d in os.environ.get("PDF_MD_PERFILES", "").split(os.pathsep) if d]

logging.getLogger("pdfminer").setLevel(logging.ERROR)


def _paginas_muestra(n):
    if n <= MAX_PAGINAS_MUESTRA:
        return list(range(n))
    paso = n / MAX_PAGINAS_MUESTRA
    return sorted({int(i * paso) for i in range(MAX_PAGINAS_MUESTRA)})


def _fraccion_lineas_partidas(page):
    """Fracción de líneas visuales que tienen un hueco horizontal ancho entre
    palabras consecutivas (señal de 2+ columnas a la misma altura)."""
    words = page.extract_words()
    if len(words) < 30:
        return 0.0
    lineas = {}
    for w in words:
        lineas.setdefault(round(w["top"] / 4), []).append(w)
    total = partidas = 0
    for ws in lineas.values():
        if len(ws) < 3:
            continue
        ws.sort(key=lambda w: w["x0"])
        total += 1
        if any(ws[i + 1]["x0"] - ws[i]["x1"] >= HUECO_COLUMNA_PT for i in range(len(ws) - 1)):
            partidas += 1
    return partidas / total if total else 0.0


def _outline(pdf):
    try:
        return list(pdf.doc.get_outlines())
    except Exception:
        return []


def _perfiles_fuente():
    """(ruta, regex de detección) de cada perfil de fuente que la declare."""
    perfiles = []
    rutas = sorted({os.path.abspath(r) for d in DIRS_PERFILES_FUENTE
                    for r in glob.glob(os.path.join(d, "*.json"))})
    for ruta in rutas:
        try:
            with open(ruta, encoding="utf-8") as f:
                deteccion = json.load(f).get("deteccion")
        except (OSError, ValueError):
            continue
        if deteccion:
            perfiles.append((ruta, re.compile(deteccion, re.IGNORECASE)))
    return perfiles


def diagnosticar(ruta):
    r = {"archivo": ruta}
    try:
        pdf = pdfplumber.open(ruta)
    except Exception as e:
        r["error"] = f"No se pudo abrir (¿dañado o cifrado?): {e}"
        r["ruta_recomendada"] = "revisar-manual"
        return r

    with pdf:
        n = len(pdf.pages)
        r["paginas"] = n
        muestra = _paginas_muestra(n)
        textos, sin_texto, partidas, tablas_pags, anchos = [], 0, [], [], []
        for i in muestra:
            p = pdf.pages[i]
            anchos.append(p.width)
            t = p.extract_text() or ""
            textos.append(t)
            if len(t.strip()) < MIN_CHARS_PAGINA_CON_TEXTO:
                sin_texto += 1
            else:
                partidas.append(_fraccion_lineas_partidas(p))
            try:
                if p.find_tables():
                    tablas_pags.append(i)
            except Exception:
                pass
        texto = "\n".join(textos)
        outline = _outline(pdf)

    r["paginas_analizadas"] = len(muestra)
    r["frac_paginas_sin_texto"] = round(sin_texto / len(muestra), 2) if muestra else 1.0
    r["articulos_detectados"] = len(ARTICULO_RE.findall(texto))
    r["tiene_tabla_contenido"] = bool(TOC_RE.search(texto)) or len(TOC_ENTRY_RE.findall(texto)) >= 5
    r["marcadores_pdf"] = len(outline)
    r["frac_lineas_en_columnas"] = round(sum(partidas) / len(partidas), 2) if partidas else 0.0
    r["pliego_horizontal"] = bool(anchos) and max(anchos) > ANCHO_PLIEGO_PT
    r["paginas_con_tablas"] = tablas_pags  # índices 0-based de pdfplumber
    r["artefactos_cid"] = len(CID_RE.findall(texto))
    r["perfiles_fuente"] = [p for p, rx in _perfiles_fuente() if rx.search(texto)]

    # --- Recomendación -----------------------------------------------------
    notas = []
    if r["frac_paginas_sin_texto"] >= 0.6:
        ruta = "ocr"
        notas.append("Casi sin texto seleccionable: probable escaneo. Mira la 1ª página "
                     "antes de aplicar OCR (puede ser un póster/archivo equivocado).")
    elif r["articulos_detectados"] >= 3:
        ruta = "normativo"
        notas.append("Texto articulado (ARTÍCULO N): usar motor_normativo / procesar_lote.")
    elif r["tiene_tabla_contenido"] or r["marcadores_pdf"] >= 3:
        ruta = "guia-por-secciones"
        notas.append("Documento por secciones: construir índice JSON "
                     "(generar_indice.py si hay marcadores) y usar guias_tecnicas.py.")
    else:
        ruta = "guia-por-secciones"
        notas.append("Sin artículos ni índice claro: construir un índice JSON a mano "
                     "(aunque sea de 1-3 secciones) y usar guias_tecnicas.py.")

    if 0 < r["frac_paginas_sin_texto"] < 0.6:
        notas.append("Algunas páginas sin texto: pueden ser imágenes/figuras o un escaneo parcial.")
    if r["frac_lineas_en_columnas"] >= 0.3 or r["pliego_horizontal"]:
        notas.append("Diseño a columnas o pliego doble: guias_tecnicas.py ya separa columnas; "
                     "revisa el orden de lectura en el .md.")
    if tablas_pags:
        notas.append(f"Tablas con grilla en páginas {tablas_pags[:15]}"
                     f"{'…' if len(tablas_pags) > 15 else ''}: extraerlas con "
                     "extraer_tablas_pdf.py y verificarlas fila por fila contra el texto.")
    if r["artefactos_cid"]:
        notas.append(f"{r['artefactos_cid']} artefactos (cid:N): fuentes de símbolos/ecuaciones; "
                     "considerar corregir_ecuaciones.py tras convertir.")

    for perfil in r["perfiles_fuente"]:
        notas.append(f"Coincide con el perfil de fuente {os.path.basename(perfil)}: "
                     f"pásalo al conversor con --perfil-fuente {perfil}")

    r["ruta_recomendada"] = ruta
    r["notas"] = notas
    return r


def _expandir(args):
    rutas = []
    for a in args:
        if os.path.isdir(a):
            rutas += sorted(glob.glob(os.path.join(a, "*.pdf")) + glob.glob(os.path.join(a, "*.PDF")))
        else:
            rutas += glob.glob(a) or [a]
    return rutas


def main():
    args = [a for a in sys.argv[1:] if a != "--json"]
    como_json = "--json" in sys.argv
    if not args:
        print(__doc__)
        sys.exit(1)

    resultados = [diagnosticar(r) for r in _expandir(args)]
    if como_json:
        print(json.dumps(resultados, ensure_ascii=False, indent=2))
        return

    for r in resultados:
        print(f"■ {r['archivo']}")
        if "error" in r:
            print(f"  ❌ {r['error']}\n")
            continue
        print(f"  páginas: {r['paginas']} (analizadas {r['paginas_analizadas']}) | "
              f"sin texto: {int(r['frac_paginas_sin_texto'] * 100)}% | "
              f"artículos: {r['articulos_detectados']} | "
              f"índice: {'sí' if r['tiene_tabla_contenido'] else 'no'} | "
              f"marcadores: {r['marcadores_pdf']} | "
              f"columnas: {int(r['frac_lineas_en_columnas'] * 100)}% | "
              f"pliego: {'sí' if r['pliego_horizontal'] else 'no'} | "
              f"tablas: {len(r['paginas_con_tablas'])} pág. | cid: {r['artefactos_cid']}")
        print(f"  → RUTA: {r['ruta_recomendada']}")
        for nota in r["notas"]:
            print(f"    · {nota}")
        print()


if __name__ == "__main__":
    main()
