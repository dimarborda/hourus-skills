#!/usr/bin/env python3
"""
formatear_tablas.py
=========================
Formatea listas/matrices de datos ya extraídas (a mano o por otro script)
como una tabla Markdown estricta y prolija: barras verticales como
delimitador de columna, encabezado + fila divisora "|---|---|...|", y
celdas alineadas con relleno de espacios para que el archivo quede legible
también en texto plano, no solo renderizado.

No reimplementa el formateo: reutiliza `tabla_a_markdown()` y
`limpiar_celda()` de `extraer_tablas_pdf.py` (misma carpeta), que ya
hacían esto para tablas extraídas de PDF con pdfplumber — esta es la
fuente única del formateo de tablas de la skill. Este script solo agrega
un CLI para darle datos que NO vienen de un PDF (ej. una lista de
coordenadas que copiaste/limpiaste a mano mientras revisás un .md).

CUÁNDO USAR ESTE SCRIPT EN VEZ DE extraer_tablas_pdf.py
--------------------------------------------------------------
- `extraer_tablas_pdf.py`: la tabla todavía está en un PDF, con grilla
  real detectable por `page.extract_tables()`.
- `formatear_tablas.py` (este): ya tenés los datos en filas/columnas
  (los armaste a mano, vienen de un JSON/CSV, o son líneas de texto con
  columnas separadas por espacios) y solo necesitás el formateo Markdown.

FORMATOS DE ENTRADA SOPORTADOS
-------------------------------
Se detectan por la extensión del archivo (o `--formato` para forzarlo):

- `.json`: una lista de listas — `[["encabezado1", "encabezado2"], ["a", "b"], ...]`.
  La primera fila es el encabezado salvo que uses `--sin-encabezado`.
- `.csv` / `.tsv`: se parsean con el módulo `csv` (delimitador `,` o
  tab según la extensión; `--delimitador` lo fuerza).
- Cualquier otra extensión, o sin archivo (lee de stdin): texto plano,
  una fila por línea, columnas separadas por 2 o más espacios/tabs
  consecutivos — el patrón típico cuando copiás una lista columnar
  extraída de un PDF (ej. "1   3° 47' 43,667" S   70° 42' 47,690" W").
  Usa `--separador` con una regex propia si tu texto usa otro delimitador
  (ej. un solo espacio, o "|").

No trunca filas: cualquier cantidad de filas se procesa completa: no hay
límite de tamaño ni recorte.

USO
---
    python3 formatear_tablas.py datos.json
    python3 formatear_tablas.py coordenadas.txt -o tabla.md
    python3 formatear_tablas.py datos.csv --delimitador ";"
    cat lista.txt | python3 formatear_tablas.py --separador "\\s{2,}"
    python3 formatear_tablas.py datos.json --sin-encabezado
    python3 formatear_tablas.py datos.json --sin-alinear

Requisitos: ninguno además de la librería estándar (csv, json, re) y
`extraer_tablas_pdf.py` en la misma carpeta.
"""

import argparse
import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extraer_tablas_pdf import tabla_a_markdown  # noqa: E402


def leer_json(contenido: str) -> list:
    datos = json.loads(contenido)
    if not isinstance(datos, list) or (datos and not isinstance(datos[0], list)):
        raise ValueError(
            "El JSON debe ser una lista de listas: [[\"col1\", \"col2\"], [\"a\", \"b\"], ...]"
        )
    return datos


def leer_csv(contenido: str, delimitador: str) -> list:
    return [fila for fila in csv.reader(contenido.splitlines(), delimiter=delimitador)]


def leer_texto_columnar(contenido: str, separador: str) -> list:
    patron = re.compile(separador)
    filas = []
    for linea in contenido.splitlines():
        if not linea.strip():
            continue
        filas.append([celda.strip() for celda in patron.split(linea.strip())])
    return filas


def detectar_formato(ruta: str) -> str:
    if not ruta:
        return "texto"
    ext = os.path.splitext(ruta)[1].lower()
    if ext == ".json":
        return "json"
    if ext == ".csv":
        return "csv"
    if ext == ".tsv":
        return "tsv"
    return "texto"


def cargar_filas(ruta: str, formato: str, delimitador: str, separador: str) -> list:
    contenido = open(ruta, encoding="utf-8").read() if ruta else sys.stdin.read()

    if formato == "json":
        return leer_json(contenido)
    if formato == "csv":
        return leer_csv(contenido, delimitador or ",")
    if formato == "tsv":
        return leer_csv(contenido, delimitador or "\t")
    return leer_texto_columnar(contenido, separador)


def main():
    parser = argparse.ArgumentParser(
        description="Formatea filas/columnas de datos como tabla Markdown estricta.",
    )
    parser.add_argument("archivo", nargs="?", help="Archivo de entrada (o vacío para leer de stdin)")
    parser.add_argument("-o", "--salida", help="Archivo de salida (por defecto: stdout)")
    parser.add_argument(
        "--formato", choices=["json", "csv", "tsv", "texto"],
        help="Fuerza el formato de entrada en vez de detectarlo por extensión",
    )
    parser.add_argument(
        "--delimitador", default=None,
        help="Delimitador para --formato csv/tsv (default: ',' o tab según formato)",
    )
    parser.add_argument(
        "--separador", default=r"\s{2,}",
        help="Regex separadora de columnas para texto plano (default: 2+ espacios/tabs)",
    )
    parser.add_argument(
        "--sin-encabezado", action="store_true",
        help="La primera fila de los datos es un dato más, no un encabezado "
             "(se generan 'Columna 1', 'Columna 2'... automáticamente)",
    )
    parser.add_argument(
        "--sin-alinear", action="store_true",
        help="No rellenar celdas con espacios para alinear columnas visualmente",
    )
    args = parser.parse_args()

    formato = args.formato or detectar_formato(args.archivo)
    filas = cargar_filas(args.archivo, formato, args.delimitador, args.separador)

    if not filas:
        print("No se encontraron filas para formatear.", file=sys.stderr)
        sys.exit(1)

    if args.sin_encabezado:
        n_cols = max(len(f) for f in filas)
        encabezado = [f"Columna {i + 1}" for i in range(n_cols)]
        filas = [encabezado] + filas

    resultado = tabla_a_markdown(filas, alinear=not args.sin_alinear)

    if args.salida:
        with open(args.salida, "w", encoding="utf-8") as f:
            f.write(resultado + "\n")
        print(f"✅ {len(filas)} fila(s) escritas en {args.salida}", file=sys.stderr)
    else:
        print(resultado)


if __name__ == "__main__":
    main()
