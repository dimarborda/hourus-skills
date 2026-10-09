#!/usr/bin/env python3
"""
extraer_tablas_pdf.py
==========================
Extrae tablas con grilla real (bordes o alineación de celda reconocible) de
un rango de páginas de un PDF, usando `pdfplumber.extract_tables()`, y las
convierte a Markdown.

POR QUÉ ES DISTINTO DE guias_tecnicas.py
----------------------------------------------
`guias_tecnicas.py` detecta y concatena COLUMNAS DE TEXTO CORRIDO
(prosa a 2-3 columnas) — funciona bien para el cuerpo de una guía técnica,
pero no entiende tablas de datos reales (ej. "NORMA | DESCRIPCIÓN", una
matriz de referencias cruzadas con "X"). Tratar una tabla real como si
fueran columnas de prosa mezcla el contenido de filas distintas, porque esa
lógica concatena cada columna de arriba a abajo completa (todas las normas,
luego todas las descripciones) en vez de emparejar fila por fila — el
resultado son fragmentos de palabras cortadas y sin relación aparente.

CUÁNDO USAR ESTE SCRIPT EN VEZ DE guias_tecnicas.py
---------------------------------------------------------
Si al revisar un `.md` generado por `guias_tecnicas.py` ves un bloque
con palabras cortadas a la mitad y fragmentos sin sentido en secuencia
(ej. "1523 de 20", "eto 4147 de 2", restos de una columna de referencias), probablemente NO es el defecto de
lectura de columnas que ya documenta `detectar_columnas()` en ese script
("Si el orden de lectura sale mezclado") — es una tabla de datos real en
esa página que el detector de columnas de prosa no puede manejar. Verifica
con `page.extract_tables()` (lo que hace este script) antes de tocar las
constantes `ANCHO_BIN_PT`/`HUECO_MINIMO_PT`/`DENSIDAD_MINIMA` de ese otro
script — ajustarlas no arregla este problema, que es de naturaleza distinta.

QUÉ HACE
--------
1. Abre el PDF y recorre el rango de páginas indicado (índices de
   pdfplumber, 0-indexados, ambos inclusive).
2. Por cada página, llama a `page.extract_tables()`.
3. Fusiona tablas "continuación" entre páginas consecutivas: si la tabla de
   la página siguiente tiene el mismo número de columnas que la anterior,
   se asume que es la misma tabla partida por salto de página (frecuente
   en tablas largas de este tipo de documento) y se concatena; si además
   repite la fila de encabezado, esa repetición se descarta.
4. Limpia el texto de cada celda (colapsa saltos de línea internos a
   espacio, escapa "|" para no romper la sintaxis de tabla Markdown).
5. Imprime el resultado como una o más tablas Markdown, listas para pegar
   en el `.md` de destino reemplazando el bloque de texto mal extraído.

QUÉ NO HACE
-----------
- No decide dónde en el `.md` pegar la tabla resultante ni la pega
  automáticamente — el layout de cada guía es distinto (secciones, chunks),
  así que ese paso es manual.
- No fusiona tablas separadas por páginas SIN tabla detectada entre medio
  (ej. una página de puro texto entre dos partes de la misma tabla): en ese
  caso trata cada tramo como tabla aparte. Poco frecuente en la práctica,
  pero revisa el resultado si el documento intercala texto narrativo en
  medio de una tabla larga.

USO
---
    python3 extraer_tablas_pdf.py archivo.pdf pagina_inicio pagina_fin

Ejemplo (una sección en las páginas impresas 28-36 de una guía con
offset_pagina_impresa=1 → índices pdfplumber 27-35):

    python3 extraer_tablas_pdf.py PDF/Procesados/mi-guia.pdf 27 35

Requisitos: pdfplumber.
"""

import sys

import pdfplumber


def limpiar_celda(texto) -> str:
    if texto is None:
        return ""
    texto = texto.replace("\n", " ").strip()
    texto = " ".join(texto.split())
    return texto.replace("|", "\\|")


def tabla_a_markdown(filas, alinear: bool = True) -> str:
    """Convierte una lista de filas (cada una, una lista de celdas) a una
    tabla Markdown estricta: primera fila = encabezado, segunda fila =
    divisor "|---|---|...", barras verticales como delimitador.

    Si `alinear` es True (default), rellena cada celda con espacios hasta
    el ancho de su columna (el más largo entre encabezado y datos) para
    que las barras verticales queden alineadas visualmente en el texto
    fuente del .md — no cambia cómo se ve renderizado (Markdown ignora
    los espacios extra), solo la legibilidad del archivo plano.

    No trunca filas: procesa listas de cualquier tamaño, y si una fila
    trae menos celdas que el máximo de columnas detectado, la completa
    con celdas vacías en vez de descartarla.
    """
    if not filas:
        return ""
    n_cols = max(len(f) for f in filas)
    celdas_por_fila = [
        [limpiar_celda(c) for c in fila] + [""] * (n_cols - len(fila))
        for fila in filas
    ]

    if alinear:
        anchos = [
            max(3, max(len(fila[c]) for fila in celdas_por_fila))
            for c in range(n_cols)
        ]
    else:
        anchos = [3] * n_cols

    lineas = []
    for i, fila in enumerate(celdas_por_fila):
        celdas = [fila[c].ljust(anchos[c]) if alinear else fila[c] for c in range(n_cols)]
        lineas.append("| " + " | ".join(celdas) + " |")
        if i == 0:
            lineas.append("| " + " | ".join("-" * anchos[c] for c in range(n_cols)) + " |")
    return "\n".join(lineas)


def extraer(pdf_path: str, pagina_inicio: int, pagina_fin: int) -> list:
    """Devuelve una lista de tablas (cada una, una lista de filas), ya
    fusionadas entre páginas consecutivas cuando corresponde."""
    tablas_fusionadas = []
    with pdfplumber.open(pdf_path) as pdf:
        for pidx in range(pagina_inicio, pagina_fin + 1):
            page = pdf.pages[pidx]
            for tabla in page.extract_tables():
                if not tabla:
                    continue
                n_cols = len(tabla[0])
                anterior = tablas_fusionadas[-1] if tablas_fusionadas else None
                if anterior and len(anterior[0]) == n_cols:
                    filas_nuevas = tabla[1:] if tabla[0] == anterior[0] else tabla
                    anterior.extend(filas_nuevas)
                else:
                    tablas_fusionadas.append(list(tabla))
    return tablas_fusionadas


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    pdf_path = sys.argv[1]
    pagina_inicio = int(sys.argv[2])
    pagina_fin = int(sys.argv[3])

    tablas = extraer(pdf_path, pagina_inicio, pagina_fin)
    print(f"<!-- {len(tablas)} tabla(s) encontradas en páginas pdfplumber "
          f"{pagina_inicio}-{pagina_fin} -->\n")
    for i, filas in enumerate(tablas):
        print(f"<!-- tabla {i + 1}: {len(filas)} filas x {len(filas[0])} columnas -->")
        print(tabla_a_markdown(filas))
        print()


if __name__ == "__main__":
    main()
