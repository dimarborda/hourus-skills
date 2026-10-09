#!/usr/bin/env python3
"""
procesar_lote.py
=====================
Orquesta la conversión masiva de PDF normativos a Markdown para RAG,
reutilizando el motor de extracción y parseo de jerarquía normativa que ya
vive en motor_normativo.py. Este script NO reimplementa esa lógica:
la importa. Si el reconocimiento de artículos o metadatos necesita ajustes,
esos cambios van en motor_normativo.py, no aquí.

QUÉ HACE
--------
1. Recorre "PDF/No procesados/" buscando archivos *.pdf (ignora archivos de
   bloqueo de otros programas, tipo ".~lock.*#", y basura de macOS como
   ".DS_Store").
2. Para cada PDF, llama a las funciones de motor_normativo.py
   (extract_pdf_text, clean_text, detect_metadata, parse_document,
   build_markdown) para generar el mismo Markdown que produciría correr ese
   script a mano sobre ese archivo.
3. Clasifica el resultado en 3 destinos, con el mismo criterio de éxito que
   ya usa motor_normativo.py en modo interactivo (¿se extrajo texto?
   ¿se reconoció al menos un artículo?):
     - Éxito         -> PDF/Procesados/<archivo>.pdf   y   md/<archivo>.md
     - Sin texto      -> PDF/Requiere-revision/<archivo>.pdf  (PDF escaneado)
     - Sin artículos  -> PDF/Requiere-revision/<archivo>.pdf  (formato no
                         reconocido por HIERARCHY_PATTERNS)
   En los dos casos de "Requiere-revision" NO se genera ni se conserva
   ningún .md: un Markdown sin artículos detectados no se puede fragmentar
   por chunk de forma útil para el RAG, así que sería peor tenerlo a medias
   en md/ que no tenerlo.
4. Registra cada fallo en PDF/Requiere-revision/NOTAS.md (fecha, archivo,
   motivo, sugerencia de siguiente paso), agregando una entrada nueva sin
   borrar el historial de corridas anteriores.
5. Imprime un resumen final: cuántos PDF quedaron procesados, cuántos en
   revisión y por qué, y cuántos campos "TODO [REVISAR]" quedaron
   pendientes de completar a mano en los .md generados con éxito.

QUÉ NO HACE (y por qué)
------------------------
- No modifica motor_normativo.py ni duplica su regex de jerarquía:
  es la fuente única de verdad del parseo normativo de esta skill.
- No aplica OCR ni reintenta automáticamente un PDF escaneado.
- No ajusta HIERARCHY_PATTERNS ni adivina campos jurídicos (modifica/deroga/
  firmante): esas decisiones siguen siendo manuales, igual que en
  motor_normativo.py.
- No borra ningún PDF original: siempre los mueve (shutil.move), nunca los
  duplica ni los elimina.
- No reprocesa lo que ya está en PDF/Procesados/ o PDF/Requiere-revision/:
  solo mira PDF/No procesados/ en cada corrida.

USO
---
    python3 procesar_lote.py [--metadatos metadatos.json] [--perfil-fuente perfil.json ...] [--sin-chunks]

Sin argumentos: usa rutas relativas al directorio de trabajo (el cwd desde
donde se invoca, o la variable de entorno PDF_MD_WORKDIR si está definida):
    PDF/No procesados/      <- cola de entrada
    PDF/Procesados/         <- destino de éxito (PDF)
    PDF/Requiere-revision/  <- destino de fallo (PDF) + NOTAS.md
    md/                     <- destino de éxito (Markdown)

Requisitos: los mismos de motor_normativo.py (pip install
pdfplumber --break-system-packages).
"""

import os
import re
import shutil
import sys
from datetime import datetime

# Reutiliza el motor de parseo existente en vez de reimplementarlo.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import motor_normativo as motor
import metadatos

# ----------------------------------------------------------------------------
# RUTAS DE TRABAJO
# ----------------------------------------------------------------------------

BASE_DIR = os.path.abspath(os.environ.get("PDF_MD_WORKDIR", os.getcwd()))
DIR_NO_PROCESADOS = os.path.join(BASE_DIR, "PDF", "No procesados")
DIR_PROCESADOS = os.path.join(BASE_DIR, "PDF", "Procesados")
DIR_REVISION = os.path.join(BASE_DIR, "PDF", "Requiere-revision")
DIR_MD = os.path.join(BASE_DIR, "md")
NOTAS_PATH = os.path.join(DIR_REVISION, "NOTAS.md")

# Archivos que no son PDF a procesar aunque aparezcan en la carpeta de
# entrada: metadatos de macOS y locks de otros programas (ej. LibreOffice
# deja ".~lock.archivo.pdf#" mientras alguien lo tiene abierto).
IGNORAR_PATRONES = (
    re.compile(r"^\.DS_Store$", re.IGNORECASE),
    re.compile(r"^\.~lock\..*#$", re.IGNORECASE),
)


def listar_pdfs_pendientes(carpeta: str) -> list:
    if not os.path.isdir(carpeta):
        return []
    pendientes = []
    for nombre in sorted(os.listdir(carpeta)):
        ruta = os.path.join(carpeta, nombre)
        if not os.path.isfile(ruta):
            continue
        if any(p.match(nombre) for p in IGNORAR_PATRONES):
            continue
        if not nombre.lower().endswith(".pdf"):
            continue
        pendientes.append(ruta)
    return pendientes


# ----------------------------------------------------------------------------
# NOTAS DE REVISIÓN MANUAL
# ----------------------------------------------------------------------------

def registrar_nota(archivo: str, motivo: str, sugerencia: str):
    """Agrega una entrada al historial NOTAS.md sin borrar corridas previas."""
    os.makedirs(DIR_REVISION, exist_ok=True)
    es_nuevo = not os.path.exists(NOTAS_PATH)
    with open(NOTAS_PATH, "a", encoding="utf-8") as f:
        if es_nuevo:
            f.write("# Notas de revisión manual — PDF/Requiere-revision\n\n")
            f.write(
                "Cada entrada corresponde a un PDF que "
                "`procesar_lote.py` no pudo convertir automáticamente. "
                "No se generó `.md` para estos casos: revisa el PDF, aplica "
                "el ajuste sugerido y vuelve a dejarlo en "
                "`PDF/No procesados/` para reintentarlo.\n\n")
        f.write(f"## {archivo}\n\n")
        f.write(f"- **Fecha:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"- **Motivo:** {motivo}\n")
        f.write(f"- **Sugerencia:** {sugerencia}\n\n")


# ----------------------------------------------------------------------------
# PROCESAMIENTO DE UN SOLO PDF
# ----------------------------------------------------------------------------

def procesar_uno(pdf_path: str, spec: dict = None) -> dict:
    """
    Devuelve un dict con el resultado de procesar un PDF:
        {"estado": "ok", "md_path": ..., "todo_count": N}
        {"estado": "sin_texto" | "sin_articulos" | "error", "motivo": "..."}
    y dentro de la misma función deja el PDF y el .md en su carpeta destino.
    """
    nombre = os.path.basename(pdf_path)
    nombre_base = os.path.splitext(nombre)[0]

    try:
        raw = motor.extract_pdf_text(pdf_path)
    except Exception as e:
        motivo = f"Error al leer el PDF con pdfplumber: {e}"
        _mover_a_revision(pdf_path, nombre)
        registrar_nota(
            nombre, motivo,
            "Verifica que el PDF no esté dañado, cifrado o protegido con "
            "contraseña (ver requisitos en el SKILL.md de pdf-a-markdown)."
        )
        return {"estado": "error", "motivo": motivo}

    if not raw.strip():
        motivo = "No se extrajo texto (probable PDF escaneado / sin texto seleccionable)."
        _mover_a_revision(pdf_path, nombre)
        registrar_nota(
            nombre, motivo,
            "Aplicar OCR (ocrmypdf o similar) y volver a dejar el PDF en "
            "'PDF/No procesados/' para reintentar. Ver SKILL.md §4 (OCR)."
        )
        return {"estado": "sin_texto", "motivo": motivo}

    text = motor.clean_text(raw)
    meta = motor.detect_metadata(text)
    valores = motor.resolver_metadatos(meta, pdf_path, spec or metadatos.cargar_spec())
    preamble, blocks, firmas_block = motor.parse_document(text, meta)

    if not blocks:
        motivo = (
            "No se reconoció ningún ARTÍCULO con el patrón actual de "
            "motor_normativo.py (HIERARCHY_PATTERNS)."
        )
        _mover_a_revision(pdf_path, nombre)
        registrar_nota(
            nombre, motivo,
            "Puede ser una norma con numeración distinta (ej. 'Artículo "
            "Primero.-') o un documento sin artículos (guía/manual). Ver "
            "SKILL.md §2-§3 antes de ajustar el script o de "
            "tratarlo con un formato de salida distinto."
        )
        return {"estado": "sin_articulos", "motivo": motivo}

    md = motor.build_markdown(meta, preamble, blocks, nombre, firmas_block)
    md = motor.finalizar_markdown(metadatos.reemplazar_front_matter(md, valores))

    os.makedirs(DIR_MD, exist_ok=True)
    md_path = os.path.join(DIR_MD, f"{nombre_base}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    os.makedirs(DIR_PROCESADOS, exist_ok=True)
    shutil.move(pdf_path, os.path.join(DIR_PROCESADOS, nombre))

    todo_count = md.count("TODO [REVISAR]") + md.count("[REVISAR")
    return {"estado": "ok", "md_path": md_path, "todo_count": todo_count}


def _mover_a_revision(pdf_path: str, nombre: str):
    os.makedirs(DIR_REVISION, exist_ok=True)
    shutil.move(pdf_path, os.path.join(DIR_REVISION, nombre))


# ----------------------------------------------------------------------------
# ORQUESTACIÓN / CLI
# ----------------------------------------------------------------------------

def main():
    args = motor.extraer_opciones_salida(motor.extraer_perfiles_fuente(sys.argv[1:]))
    spec = metadatos.cargar_spec(args[args.index("--metadatos") + 1] if "--metadatos" in args else None)
    pendientes = listar_pdfs_pendientes(DIR_NO_PROCESADOS)
    if not pendientes:
        print(f"No hay PDF pendientes en '{DIR_NO_PROCESADOS}'.")
        return

    print(f"Procesando {len(pendientes)} PDF de 'PDF/No procesados/'...\n")

    resultados = {"ok": [], "sin_texto": [], "sin_articulos": [], "error": []}

    for pdf_path in pendientes:
        nombre = os.path.basename(pdf_path)
        print(f"→ {nombre}")
        try:
            resultado = procesar_uno(pdf_path, spec)
        except Exception as e:
            motivo = f"Excepción no controlada: {e}"
            print(f"  ❌ {motivo}")
            _mover_a_revision(pdf_path, nombre)
            registrar_nota(
                nombre, motivo,
                "Revisar manualmente el PDF y, si el error se repite, "
                "reportarlo para ajustar procesar_lote.py o "
                "motor_normativo.py."
            )
            resultados["error"].append((nombre, motivo))
            continue

        estado = resultado["estado"]
        if estado == "ok":
            print(f"  ✅ OK -> md/{nombre.rsplit('.', 1)[0]}.md "
                  f"(TODO [REVISAR] pendientes: {resultado['todo_count']})")
            resultados["ok"].append((nombre, resultado["todo_count"]))
        else:
            print(f"  ⚠️  Requiere revisión: {resultado['motivo']}")
            resultados[estado].append((nombre, resultado["motivo"]))
        print()

    # --- Resumen final ---
    total = len(pendientes)
    n_ok = len(resultados["ok"])
    n_revision = total - n_ok
    print("=" * 60)
    print(f"Resumen: {total} PDF procesados este lote")
    print(f"  ✅ Convertidos a Markdown : {n_ok}")
    print(f"  ⚠️  Requieren revisión     : {n_revision}")
    if resultados["ok"]:
        total_todo = sum(c for _, c in resultados["ok"])
        print(f"     (TODO [REVISAR] pendientes en total: {total_todo})")
    for estado in ("sin_texto", "sin_articulos", "error"):
        for nombre, motivo in resultados[estado]:
            print(f"     - {nombre}: {motivo}")
    if n_revision:
        print(f"\nDetalle completo en: {NOTAS_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    main()
