#!/usr/bin/env python3
"""
guias_tecnicas.py
=======================
Convierte guías técnicas (manuales, guías de implementación, informes
por secciones) en Markdown estructurado para RAG. Es el equivalente de
motor_normativo.py pero para un tipo de documento muy distinto: en
vez de CAPÍTULO > SECCIÓN > ARTÍCULO con texto corrido a una columna, estas
guías suelen ser diseños editoriales a 2-3 columnas, con íconos, imágenes y
recuadros — sin ningún "ARTÍCULO N°" que reconocer. Por eso no se intentó
forzarlas por motor_normativo.py (terminan en
"PDF/Requiere-revision/" con el motivo "no se reconoció ningún ARTÍCULO").

CÓMO FUNCIONA (y por qué necesita un "índice" a mano)
-------------------------------------------------------
Un decreto se puede trocear automáticamente porque "ARTÍCULO 5°." es un
patrón 100% regular. Una guía como esta NO tiene un patrón así de
confiable: sus subtítulos son preguntas o frases en negrita sin numeración
("¿Qué es...?", "¿Cómo se aplica...?").

Lo que SÍ es 100% confiable en este tipo de documento es su tabla de
contenido ("CONTENIDO"): trae el título exacto de cada sección de primer
nivel y la página impresa donde empieza. Por eso este script no adivina la
ESTRUCTURA del PDF (qué sección viene después de cuál): la recibe de un
archivo "índice" (JSON, uno por guía, en
"PDF/indices-guias/<nombre-del-pdf>.indice.json") que alguien llena UNA vez
leyendo el índice impreso del documento (2-3 minutos). A partir de ahí,
todo lo demás es mecánico — incluyendo, ahora, la detección de columnas
(ver más abajo, punto 3): eso sí se automatizó, no se necesita indicarlo a
mano.

QUÉ HACE
--------
1. Lee el índice JSON: título del documento, metadatos, y la lista de
   secciones de primer nivel con su página impresa de inicio.
2. Calcula el rango de páginas de cada sección (de su página de inicio a
   la de la siguiente sección) usando el "offset_pagina_impresa" del índice
   para traducir página impresa -> índice de página de pdfplumber.
3. Para cada página, DETECTA las columnas de texto reales (función
   detectar_columnas): mira dónde caen las palabras de la página (su
   coordenada x0) y encuentra los huecos verticales sin texto que separan
   una columna de la siguiente — no asume un número fijo de columnas de
   ancho igual. Esto reemplazó un primer intento más simple (recortar la
   página en N franjas de ancho igual, con N fijado a mano por sección) que
   resultó estar mal: en este documento las columnas de texto casi nunca
   ocupan el ancho completo de la página (queda espacio para imágenes o
   íconos), así que un corte a ciegas por fracciones iguales terminaba
   partiendo una columna real por la mitad y mezclando su contenido con el
   de la columna vecina en la misma línea — exactamente el defecto que se
   detectó al revisar el .md generado con la primera versión. Luego
   concatena el texto columna por columna (no línea por línea), para no
   intercalar contenido de columnas distintas que caen a la misma altura.
4. Limpia números de página sueltos reutilizando
   motor_normativo.clean_text.
5. Descarta los "fragmentos huérfanos" que aun así deja el recorte por
   columnas: líneas de 1-2 caracteres sueltos que en la práctica resultan
   ser pedazos del título grande y decorativo de cada sección (letras
   apiladas tipo cartel) atrapados por el recorte geométrico en la página
   de inicio de cada sección. Se probó primero ampliar el recorte de cada
   columna (solapamiento) para evitar que una palabra quedara cortada a la
   mitad, pero en la práctica eso arrastraba texto de la columna vecina
   hacia líneas que antes estaban limpias — empeoraba el resultado en vez
   de mejorarlo. Como el título real de la sección ya viene del índice (no
   de este texto extraído), descartar esas líneas sueltas no pierde
   información: solo quita ruido.
6. Si una sección resulta muy larga, la subdivide con
   motor_normativo.split_long_block (mismo criterio de
   MAX_CHUNK_CHARS que ya usan los decretos) para no generar chunks
   gigantes.
7. Genera un Markdown con el mismo lenguaje de marcado que ya usa
   motor_normativo.py: front-matter YAML, encabezados jerárquicos,
   breadcrumb "**Ruta:** ..." y marcas <!-- CHUNK id="..." ruta="..." -->
   — así el resto del pipeline de RAG no necesita distinguir si un chunk
   vino de un decreto o de una guía.

QUÉ NO HACE (y por qué)
------------------------
- No detecta subtítulos DENTRO de cada sección (los "¿Qué es...?" en
  negrita). Detectarlos de forma confiable requeriría analizar el tamaño y
  peso de fuente de cada carácter del PDF, no solo el texto — se dejó
  fuera por complejidad/beneficio: cada sección de primer nivel ya queda
  como un chunk temáticamente completo (o varios, si es larga, partidos por
  tamaño, nunca a mitad de párrafo gracias a split_long_block), que es lo
  que de verdad importa para no perder contexto en el RAG.
- La detección de columnas (detectar_columnas) sigue siendo una heurística
  geométrica (huecos sin texto entre bloques de palabras), no una lectura
  real del diseño de la página. Funciona bien en la inmensa mayoría de
  páginas de este documento (columnas rectas, sin texto que fluya
  alrededor de una imagen en forma irregular), pero puede fallar en casos
  atípicos: citas en recuadro con sangría propia dentro de una columna
  (puede detectarse como un tramo aparte, generalmente inofensivo porque
  igual queda en su lugar aproximado), o páginas con muy poco texto en
  alguna columna (por debajo de DENSIDAD_MINIMA, se descarta esa columna
  completa). Si al revisar el .md generado una sección se ve con el orden
  de lectura mezclado, ajusta las constantes ANCHO_BIN_PT / HUECO_MINIMO_PT
  / DENSIDAD_MINIMA al inicio del script (o avisa para revisar esa página
  puntual) y vuelve a correr.
- No decide qué PDF de "PDF/Requiere-revision/" es una guía técnica válida
  (con índice numerado y páginas) vs. un archivo simplemente equivocado en
  el catálogo. Esa decisión es humana (ver §1 de SKILL.md).

USO
---
    python3 guias_tecnicas.py PDF/Requiere-revision/mi-guia.pdf \\
        PDF/indices-guias/mi-guia.indice.json [--metadatos metadatos.json] \\
        [--perfil-fuente perfil.json] [--sin-chunks]

Si el índice no existe todavía, genéralo con generar_indice.py (si el PDF
tiene marcadores) o créalo a mano a partir de
SKILL_DIR/assets/plantilla.indice.json.

Requisitos: los mismos de motor_normativo.py (pdfplumber).
"""

import json
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import motor_normativo as motor
import metadatos

BASE_DIR = os.path.abspath(os.environ.get("PDF_MD_WORKDIR", os.getcwd()))
DIR_PROCESADOS = os.path.join(BASE_DIR, "PDF", "Procesados")
DIR_MD = os.path.join(BASE_DIR, "md")


import math

# --- Detección automática de columnas reales por página --------------------
#
# Primera versión de este script: asumía que las columnas dividen la página
# en franjas de ANCHO IGUAL (page.width / n_columnas), con el número de
# columnas fijado a mano por sección en el índice JSON. Se comprobó que esto
# es incorrecto para este documento: las columnas de texto reales casi nunca
# ocupan el ancho completo de la página (queda espacio para imágenes,
# íconos o márgenes variables), así que un corte "a ciegas" a la mitad o a
# los tercios de la página termina cortando una columna real por la mitad
# — mezclando en una misma línea el final de una columna con el principio
# de la siguiente, que es justo el defecto que se detectó al revisar el
# .md generado (líneas como "...normatizada procesos – objetivos que pe").
#
# La alternativa que sí funciona: mirar dónde caen realmente las palabras
# de la página (su coordenada x0) y encontrar los huecos verticales sin
# texto que separan una columna real de la siguiente — el mismo principio
# que usaría un humano para "ver" las columnas, pero medido en vez de
# asumido con una fracción del ancho de página.
ANCHO_BIN_PT = 4       # resolución del histograma de posiciones x0
HUECO_MINIMO_PT = 14   # ancho mínimo de un hueco para contar como separación real de columna
DENSIDAD_MINIMA = 12   # palabras mínimas en un tramo para contar como columna (filtra ruido de leyendas de foto sueltas)
MARGEN_FRAC = 0.02     # ignora huecos pegados al borde izq/der de la página


def detectar_columnas(page) -> list:
    """Devuelve una lista de tramos (x0, x1) — uno por columna de texto real
    detectada en la página, de izquierda a derecha. Un tramo con muy pocas
    palabras (p. ej. la leyenda suelta de una foto) se descarta: no es una
    columna de contenido, es ruido.
    """
    words = page.extract_words()
    if not words:
        return [(0, page.width)]

    n_bins = int(page.width // ANCHO_BIN_PT) + 1
    counts = [0] * n_bins
    for w in words:
        idx = int(w["x0"] // ANCHO_BIN_PT)
        if 0 <= idx < n_bins:
            counts[idx] += 1

    margen = int(n_bins * MARGEN_FRAC)
    bins_hueco = max(1, math.ceil(HUECO_MINIMO_PT / ANCHO_BIN_PT))

    tramos = []
    i = margen
    while i < n_bins - margen:
        if counts[i] == 0:
            i += 1
            continue
        j = i
        while j < n_bins - margen:
            if counts[j] == 0 and all(c == 0 for c in counts[j:j + bins_hueco]):
                break
            j += 1
        tramos.append((i, j))
        i = j
        while i < n_bins - margen and counts[i] == 0:
            i += 1

    tramos_validos = [
        (a * ANCHO_BIN_PT, b * ANCHO_BIN_PT)
        for a, b in tramos
        if sum(counts[a:b]) >= DENSIDAD_MINIMA
    ]
    return tramos_validos or [(0, page.width)]


def extraer_texto_columnas(page, y_tol=6, gap_threshold=14) -> str:
    """Detecta dinámicamente las columnas y pliegos impresos de la página,
    extrayendo el texto ordenadamente columna por columna completa sin mezclar líneas
    de columnas vecinas a la misma altura.
    """
    words = page.extract_words()
    if not words:
        return ""

    is_spread = page.width > 800
    sides = []
    if is_spread:
        mid_x = page.width / 2
        sides.append((0, mid_x))
        sides.append((mid_x, page.width))
    else:
        sides.append((0, page.width))

    blocks = []
    for min_x, max_x in sides:
        side_words = [w for w in words if min_x <= w["x0"] < max_x]
        if not side_words:
            continue

        side_lines = []
        for w in sorted(side_words, key=lambda x: (x["top"], x["x0"])):
            matched = False
            for line in side_lines:
                if abs(w["top"] - line["top"]) < y_tol:
                    line["words"].append(w)
                    matched = True
                    break
            if not matched:
                side_lines.append({"top": w["top"], "words": [w]})

        col1_text = []
        col2_text = []
        mid_side = (min_x + max_x) / 2

        for l in side_lines:
            l_words = sorted(l["words"], key=lambda x: x["x0"])
            split_idx = -1
            for i in range(len(l_words) - 1):
                gap = l_words[i+1]["x0"] - l_words[i]["x1"]
                if gap >= gap_threshold:
                    split_idx = i + 1
                    break

            if split_idx != -1:
                t1 = " ".join([w["text"] for w in l_words[:split_idx]])
                t2 = " ".join([w["text"] for w in l_words[split_idx:]])
                col1_text.append(t1)
                col2_text.append(t2)
            else:
                t = " ".join([w["text"] for w in l_words])
                line_x0 = l_words[0]["x0"]
                line_x1 = l_words[-1]["x1"]

                # Verificar si es una línea de ancho completo (encabezado o título que cruza la página)
                if line_x0 < min_x + (max_x - min_x) * 0.25 and line_x1 > min_x + (max_x - min_x) * 0.75:
                    if col1_text or col2_text:
                        if col1_text: blocks.append("\n".join(col1_text))
                        if col2_text: blocks.append("\n".join(col2_text))
                        col1_text, col2_text = [], []
                    blocks.append(t)
                elif line_x0 >= mid_side:
                    col2_text.append(t)
                else:
                    col1_text.append(t)

        if col1_text: blocks.append("\n".join(col1_text))
        if col2_text: blocks.append("\n".join(col2_text))

    return "\n\n".join(blocks)


import re

# Patrón de "fragmento huérfano": una línea de 1-2 letras (con o sin guion/
# coma pegado) o un signo de puntuación suelto. En este tipo de documento
# (diseño editorial a columnas con títulos grandes decorativos apilados),
# el recorte por columnas geométrico a veces atrapa 1-2 caracteres sueltos
# del título grande de la sección o de una leyenda/foto vecina, que quedan
# como su propia "línea" sin pertenecer a ninguna palabra real del cuerpo
# del texto. Se probó ampliar el recorte de cada columna (solapamiento)
# para evitar el corte, pero en la práctica arrastraba MÁS ruido (texto de
# la columna vecina pegado a líneas reales) sin recuperar la palabra
# perdida — así que en vez de intentar reconstruir la palabra original
# (no es posible de forma confiable), se descarta el fragmento como ruido.
# El título de cada sección ya viene del índice (no de este texto), así que
# no se pierde información real al quitar estas líneas.
PATRON_FRAGMENTO_HUERFANO = re.compile(
    r"^(?:[A-Za-zÁÉÍÓÚÑÜáéíóúñü]{1,2}[-,]?|[-,])$"
)


def limpiar_fragmentos_huerfanos(texto: str) -> str:
    lineas = texto.split("\n")
    limpias = [ln for ln in lineas if not PATRON_FRAGMENTO_HUERFANO.match(ln.strip())]
    return "\n".join(limpias)


# Encabezados y pies de página repetidos (título del libro, autor, nombre
# del capítulo, "Manual X · pág. 12"): una línea que aparece entre las
# LINEAS_BORDE primeras o últimas de al menos MIN_PAGINAS_REPETIDA páginas
# es ruido de página, no contenido. Los dígitos se ignoran al comparar para
# que "12 · Mi libro" y "13 · Mi libro" cuenten como la misma línea.
LINEAS_BORDE = 2
MIN_PAGINAS_REPETIDA = 3


def _clave_linea(linea: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", linea)).strip().lower()


def detectar_lineas_repetidas(pdf) -> set:
    """Claves (ver _clave_linea) de las líneas que se repiten en el borde
    superior o inferior de varias páginas."""
    conteo = {}
    for page in pdf.pages:
        lineas = [l.strip() for l in (page.extract_text() or "").split("\n") if l.strip()]
        borde = set(lineas[:LINEAS_BORDE] + lineas[-LINEAS_BORDE:])
        for l in borde:
            clave = _clave_linea(l)
            if len(re.sub(r"[^a-záéíóúñü]", "", clave)) >= 4:
                conteo[clave] = conteo.get(clave, 0) + 1
    return {c for c, n in conteo.items() if n >= MIN_PAGINAS_REPETIDA}


def quitar_lineas_repetidas(texto: str, repetidas: set) -> str:
    if not repetidas:
        return texto
    return "\n".join(l for l in texto.split("\n") if _clave_linea(l) not in repetidas)


def cargar_indice(ruta_indice: str) -> dict:
    with open(ruta_indice, "r", encoding="utf-8") as f:
        return json.load(f)


def extraer_secciones(pdf, indice: dict) -> list:
    """Devuelve una lista de dicts {titulo, numero, ruta, body} — uno por
    sección de primer nivel del índice, con el texto ya extraído y
    limpio."""
    offset = indice.get("offset_pagina_impresa", 1)
    secciones = indice["secciones"]
    total_paginas = len(pdf.pages)
    repetidas = detectar_lineas_repetidas(pdf)
    resultado = []

    for i, sec in enumerate(secciones):
        inicio_impreso = sec["pagina_impresa_inicio"]
        inicio_idx = inicio_impreso - offset
        if i + 1 < len(secciones):
            fin_idx = secciones[i + 1]["pagina_impresa_inicio"] - offset
        else:
            fin_idx = total_paginas

        inicio_idx = max(0, inicio_idx)
        fin_idx = min(total_paginas, fin_idx)

        textos_pagina = []
        for pidx in range(inicio_idx, fin_idx):
            page = pdf.pages[pidx]
            textos_pagina.append(extraer_texto_columnas(page))
        raw = quitar_lineas_repetidas("\n\n".join(textos_pagina), repetidas)
        body = motor.clean_text(raw)
        body = limpiar_fragmentos_huerfanos(body)

        if sec.get("numero"):
            titulo_seccion = f"Sección {sec['numero']} – {sec['titulo']}"
        else:
            titulo_seccion = sec["titulo"]

        resultado.append({
            "titulo": titulo_seccion,
            "body": body,
            "paginas": (inicio_impreso, secciones[i + 1]["pagina_impresa_inicio"] - 1
                        if i + 1 < len(secciones) else None),
        })

    return resultado


def resolver_metadatos(indice: dict, ruta_pdf: str, spec: dict) -> dict:
    """Spec del usuario + campos del índice JSON + propiedades del PDF."""
    detectados = {k: v for k, v in metadatos.info_pdf(ruta_pdf).items() if v}
    detectados.update({k: v for k, v in indice.items()
                       if k != "secciones" and not k.startswith("_") and metadatos._detectado(v)})
    return metadatos.resolver(spec, detectados, os.path.basename(ruta_pdf))


def build_markdown(indice: dict, secciones: list, ruta_pdf: str, spec: dict = None) -> str:
    spec = spec or metadatos.cargar_spec()
    out = []
    titulo_doc = indice["titulo"]

    valores = resolver_metadatos(indice, ruta_pdf, spec)
    out.append(metadatos.front_matter(valores))
    out.append("")
    out.append(f"# {titulo_doc}")
    out.append("")
    out.append(f"**Ruta:** {titulo_doc}")
    out.append("")

    for sec in secciones:
        titulo_seccion = sec["titulo"]
        ruta = f"{titulo_doc} > {titulo_seccion}"
        sub_bodies = motor.split_long_block(sec["body"], motor.MAX_CHUNK_CHARS)

        for idx, sub_body in enumerate(sub_bodies):
            suffix = "" if len(sub_bodies) == 1 else f"-p{idx+1}"
            chunk_ruta = ruta if len(sub_bodies) == 1 else f"{ruta} (parte {idx+1}/{len(sub_bodies)})"
            chunk_id = f"{motor.slugify(titulo_doc)}-{motor.slugify(titulo_seccion)}{suffix}"

            out.append(f'<!-- CHUNK id="{chunk_id}" ruta="{chunk_ruta}" -->')
            out.append("")
            if idx == 0:
                out.append(f"## {titulo_seccion}")
                out.append("")
            out.append(f"**Ruta:** {chunk_ruta}")
            out.append("")
            out.append(sub_body if sub_body.strip() else "[REVISAR: sección vacía o no extraída]")
            out.append("")
            out.append("<!-- /CHUNK -->")
            out.append("")

    return "\n".join(out)


def main():
    args = motor.extraer_opciones_salida(motor.extraer_perfiles_fuente(sys.argv[1:]))
    ruta_spec = None
    if "--metadatos" in args:
        i = args.index("--metadatos")
        ruta_spec = args[i + 1]
        args = args[:i] + args[i + 2:]
    if len(args) != 2:
        print(__doc__)
        sys.exit(1)

    ruta_pdf, ruta_indice = args
    spec = metadatos.cargar_spec(ruta_spec)

    print(f"[1/3] Leyendo índice: {ruta_indice}")
    indice = cargar_indice(ruta_indice)
    # Si el usuario fija el título en la spec, manda también en H1 y rutas.
    titulo_spec = spec["campos"].get("titulo")
    if titulo_spec not in ("auto", None, False):
        indice["titulo"] = titulo_spec

    print(f"[2/3] Extrayendo texto por secciones de: {ruta_pdf}")
    import pdfplumber
    with pdfplumber.open(ruta_pdf) as pdf:
        secciones = extraer_secciones(pdf, indice)

    for sec in secciones:
        pag_ini, pag_fin = sec["paginas"]
        rango = f"{pag_ini}-{pag_fin}" if pag_fin else f"{pag_ini}-fin"
        print(f"    - {sec['titulo']} (págs. {rango}, {len(sec['body'])} caracteres)")

    print("[3/3] Escribiendo Markdown...")
    nombre_archivo = os.path.basename(ruta_pdf)
    nombre_base = os.path.splitext(nombre_archivo)[0]
    md = motor.finalizar_markdown(build_markdown(indice, secciones, ruta_pdf, spec))

    os.makedirs(DIR_MD, exist_ok=True)
    md_path = os.path.join(DIR_MD, f"{nombre_base}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"  ✅ Listo: {md_path}")

    # Solo se mueve el PDF si vive dentro de la estructura de lote del
    # directorio de trabajo (PDF/...). Un PDF suelto de otra carpeta del
    # usuario se deja donde está.
    dir_pdf = os.path.join(BASE_DIR, "PDF") + os.sep
    if os.path.abspath(ruta_pdf).startswith(dir_pdf):
        os.makedirs(DIR_PROCESADOS, exist_ok=True)
        destino_pdf = os.path.join(DIR_PROCESADOS, nombre_archivo)
        if os.path.exists(ruta_pdf) and os.path.abspath(ruta_pdf) != os.path.abspath(destino_pdf):
            shutil.move(ruta_pdf, destino_pdf)
        print(f"  ✅ PDF en: PDF/Procesados/{nombre_archivo}")


if __name__ == "__main__":
    main()
