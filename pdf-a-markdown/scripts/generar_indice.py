#!/usr/bin/env python3
"""
generar_indice.py
==================
Genera el borrador del índice JSON que necesita guias_tecnicas.py, para
que nadie tenga que escribirlo a mano. Prueba, en este orden:

1. MARCADORES (bookmarks / outline) embebidos en el PDF: lo más confiable
   cuando existen (PDF exportados desde Word/InDesign).
2. TABLA DE CONTENIDO IMPRESA: lee las entradas "Título ..... 12" (también
   "Pág. 12", títulos envueltos en 2 líneas e índices a dos columnas) y
   UBICA cada sección buscando su título en las páginas del PDF. No se
   asume un desfase fijo entre página impresa y página del PDF: se ajusta
   la relación página impresa -> página del PDF (incluidos pliegos dobles,
   donde cada página del PDF trae dos impresas) con los títulos que sí se
   encuentran, y cada sección toma la página donde aparece su título.
3. ENCABEZADO CORRIDO: si no hay índice, usa la primera línea de cada
   página ("Manual X — Capítulo 3 — Alcance") y abre una sección cada vez
   que cambia.

En los tres casos el borrador sale con "offset_pagina_impresa": 0 (las
páginas ya son índices 0-based de pdfplumber), así que no hay que calcular
ningún offset. Lo dudoso queda listado en "_revisar" para que el agente lo
compruebe mirando esas páginas. Si nada funciona, escribe un esqueleto de
una sección (ver references/indice-json.md).

USO
---
    python3 generar_indice.py documento.pdf                  # -> documento.indice.json al lado
    python3 generar_indice.py documento.pdf salida.json
    python3 generar_indice.py documento.pdf --nivel-max 2    # incluye subsecciones

Por defecto solo toma marcadores de nivel 1 (secciones de primer nivel),
que es el grano de chunk que usa guias_tecnicas.py.

SIEMPRE revisa el borrador: título del documento, títulos de sección (la
tabla de contenido suele venir en MAYÚSCULAS) y las entradas de "_revisar".

Requisitos: pip install pdfplumber
"""

import json
import logging
import math
import os
import re
import sys
import unicodedata
from collections import Counter

import pdfplumber
from pdfminer.pdftypes import resolve1
from pdfminer.psparser import PSLiteral

logging.getLogger("pdfminer").setLevel(logging.ERROR)


def _mapa_paginas(pdf):
    return {p.page_obj.pageid: i for i, p in enumerate(pdf.pages)}


def _resolver_destino(doc, dest, accion):
    if dest is None and accion is not None:
        accion = resolve1(accion)
        if isinstance(accion, dict):
            dest = accion.get("D")
    dest = resolve1(dest)
    if isinstance(dest, (bytes, str, PSLiteral)):
        nombre = dest.name if isinstance(dest, PSLiteral) else dest
        try:
            dest = resolve1(doc.get_dest(nombre))
        except Exception:
            return None
    if isinstance(dest, dict):
        dest = resolve1(dest.get("D"))
    if isinstance(dest, list) and dest:
        ref = dest[0]
        return getattr(ref, "objid", None)
    return None


# ----------------------------------------------------------------------------
# 1. Marcadores
# ----------------------------------------------------------------------------

def _desde_marcadores(pdf, nivel_max):
    mapa = _mapa_paginas(pdf)
    doc = pdf.doc
    secciones = []
    try:
        outlines = list(doc.get_outlines())
    except Exception:
        outlines = []
    for nivel, titulo, dest, accion, _se in outlines:
        if nivel > nivel_max:
            continue
        objid = _resolver_destino(doc, dest, accion)
        pagina = mapa.get(objid)
        if pagina is None:
            continue
        secciones.append({
            "nivel": nivel,
            "numero": None,
            "titulo": (titulo or "").strip(),
            "pagina_impresa_inicio": pagina,
        })
    secciones.sort(key=lambda s: s["pagina_impresa_inicio"])
    return secciones


# ----------------------------------------------------------------------------
# 2. Tabla de contenido impresa
# ----------------------------------------------------------------------------

# Páginas iniciales donde se busca la tabla de contenido.
MAX_PAGINAS_TOC = 30
# Mínimo de entradas para considerar que una página es de índice.
MIN_ENTRADAS_TOC = 3
# Una entrada: texto + puntos guía (3+) + número de página, opcionalmente
# precedido de "Pág."/"p.". Puede haber dos por línea (índice a 2 columnas).
ENTRADA_TOC_RE = re.compile(
    r"(?P<titulo>\S.*?)\s*(?:\.\s?){3,}\s*(?:p[áa]g(?:ina)?\.?\s*|p\.\s*)?(?P<pagina>\d{1,4})\b",
    re.IGNORECASE,
)
# Entrada SIN puntos guía, habitual en libros ("Capítulo 3  El viaje  45"):
# solo se busca en páginas que ya se sabe que son de índice (traen el
# encabezado "Contenido"/"Índice" o siguen a otra página de índice), porque
# en el cuerpo del texto muchas líneas terminan en número.
ENTRADA_SIN_PUNTOS_RE = re.compile(r"^(?P<titulo>\S.*?[^\d\s])\s+(?P<pagina>\d{1,4})$")
# "Capítulo 3" solo no es una entrada con página 3.
SOLO_ROTULO_RE = re.compile(r"(?:cap[íi]tulo|parte|libro|secci[óo]n|anexo|ap[ée]ndice)$", re.IGNORECASE)
NUMERO_RE = re.compile(r"^(?P<numero>\d+(?:\.\d+)*)\.?\s+(?P<resto>\S.*)$")
ENCABEZADO_TOC_RE = re.compile(
    r"^(?:tabla\s+de\s+)?(?:contenidos?|[íi]ndice(?:\s+general)?)\s*$", re.IGNORECASE
)
# Ítems de las listas de tablas/figuras (no son secciones de contenido).
ITEM_LISTA_RE = re.compile(
    r"^(?:tabla|figura|gr[áa]fic[oa]|ilustraci[óo]n|mapa|cuadro|imagen|foto)\s+[\dIVX]",
    re.IGNORECASE,
)
ANCHO_PLIEGO_PT = 800  # mismo umbral que guias_tecnicas.py
# Relaciones página impresa -> página del PDF que se prueban: una página
# impresa por página del PDF, o dos (pliego doble).
PENDIENTES_PAGINA = (1.0, 0.5)


def _norm(texto):
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def _claves_titulo(titulo):
    """(clave corta, clave larga): primeras 2 y 6 palabras del título
    normalizado. El título de una sección suele venir partido en varias
    líneas o mezclado con la columna vecina, pero su comienzo abre una
    línea de la página (clave corta); si además el texto de la página trae
    las 6 primeras palabras seguidas, la coincidencia es fuerte."""
    palabras = _norm(titulo).split()
    return " ".join(palabras[:2]), " ".join(palabras[:6])


def _inicios_de_linea(texto):
    """Comienzo normalizado de cada línea, sin numeración delante
    ("5 RESPONSABLES..." -> "responsables ...")."""
    return [re.sub(r"^(?:\d+ )+", "", _norm(l)) for l in texto.split("\n") if l.strip()]


def _texto_para_indice(page):
    """Texto de una página de índice. En un pliego doble cuyo centro no cruza
    ninguna palabra (índice a dos columnas, una por página impresa), cada
    mitad por separado: si no, las dos columnas salen mezcladas línea a
    línea."""
    mitad = page.width / 2
    if page.width <= ANCHO_PLIEGO_PT or any(
        w["x0"] < mitad - 5 and w["x1"] > mitad + 5 for w in page.extract_words()
    ):
        return page.extract_text() or ""
    return "\n".join(
        page.crop((x0, 0, x1, page.height)).extract_text() or ""
        for x0, x1 in ((0, mitad), (mitad, page.width))
    )


def _leer_entradas(lineas, buscar):
    """[(titulo, pagina_impresa)] de las líneas de una página de índice;
    `buscar(linea)` devuelve los matches (con grupos titulo/pagina)."""
    en_pagina, pendiente = [], ""
    for linea in lineas:
        encontradas = buscar(linea)
        if not encontradas:
            # Posible primera línea de un título envuelto en dos líneas.
            pendiente = "" if ENCABEZADO_TOC_RE.match(linea) else linea
            continue
        for k, m in enumerate(encontradas):
            titulo = m.group("titulo").strip()
            # Se une con la línea anterior solo si esta trae la numeración y
            # la entrada no, o si la entrada arranca en minúscula
            # (continuación evidente).
            if k == 0 and pendiente and (
                (NUMERO_RE.match(pendiente) and not NUMERO_RE.match(titulo))
                or titulo[:1].islower()
            ):
                titulo = f"{pendiente} {titulo}"
            en_pagina.append((titulo, int(m.group("pagina"))))
        pendiente = ""
    return en_pagina


def _entradas_toc(textos):
    """Devuelve (entradas, paginas_toc). Cada entrada: {titulo, numero,
    nivel, pagina_impresa}."""
    entradas, paginas_toc = [], []
    for idx, texto in enumerate(textos[:MAX_PAGINAS_TOC]):
        lineas = [l.strip() for l in texto.split("\n") if l.strip()]
        en_pagina = _leer_entradas(lineas, lambda l: list(ENTRADA_TOC_RE.finditer(l)))
        if len(en_pagina) < MIN_ENTRADAS_TOC and (
            any(ENCABEZADO_TOC_RE.match(l) for l in lineas) or idx - 1 in paginas_toc
        ):
            def sin_puntos(linea):
                m = ENTRADA_SIN_PUNTOS_RE.match(linea)
                return [m] if m and not SOLO_ROTULO_RE.search(m.group("titulo")) else []
            candidatas = _leer_entradas(lineas, sin_puntos)
            paginas = [p for _, p in candidatas]
            crecientes = sum(1 for x, y in zip(paginas, paginas[1:]) if y >= x)
            if len(candidatas) >= MIN_ENTRADAS_TOC and crecientes >= 0.7 * (len(paginas) - 1):
                en_pagina = candidatas
        if len(en_pagina) >= MIN_ENTRADAS_TOC:
            paginas_toc.append(idx)
            for titulo, pagina in en_pagina:
                titulo = re.sub(r"\s+", " ", titulo).strip(" .-–—")
                numero, nivel = None, 1
                m = NUMERO_RE.match(titulo)
                if m:
                    numero, titulo = m.group("numero"), m.group("resto").strip(" .-–—")
                    nivel = numero.count(".") + 1
                if ITEM_LISTA_RE.match(titulo) or len(_norm(titulo)) < 3 or titulo[:1].islower():
                    continue
                entradas.append({"titulo": titulo, "numero": numero, "nivel": nivel,
                                 "pagina_impresa": pagina})
    return entradas, paginas_toc


def _desde_toc(textos, textos_toc, nivel_max):
    entradas, paginas_toc = _entradas_toc(textos_toc)
    entradas = [e for e in entradas if e["nivel"] <= nivel_max]
    if len(entradas) < 2:
        return [], []
    entradas.sort(key=lambda e: e["pagina_impresa"])

    n = len(textos)
    lineas = [_inicios_de_linea(t) for t in textos]
    planos = [" ".join(ls) for ls in lineas]
    toc = set(paginas_toc)
    # Páginas (fuera del índice) con una línea que abre con el título:
    # fuertes si además traen sus 6 primeras palabras seguidas.
    fuertes, debiles = [], []
    for e in entradas:
        corta, larga = _claves_titulo(e["titulo"])
        abre = [i for i in range(n) if i not in toc and corta
                and any(l == corta or l.startswith(corta + " ") for l in lineas[i])]
        fuertes.append([i for i in abre if larga in planos[i]])
        debiles.append(abre)
    def estimar(a, b, pagina):
        return math.floor(a * pagina + b)

    # Relación página impresa -> página del PDF que explica más títulos con
    # coincidencia exacta (fuertes valen doble). En un pliego doble cada
    # página del PDF trae dos impresas, por eso b avanza de 0.5 en 0.5.
    mejor = (-1, 1.0, 0.0)
    for a in PENDIENTES_PAGINA:
        for b2 in range(-2 * n, 2 * n):
            b = b2 / 2
            puntos = sum(
                2 * (estimar(a, b, e["pagina_impresa"]) in f) + (estimar(a, b, e["pagina_impresa"]) in d)
                for e, f, d in zip(entradas, fuertes, debiles)
            )
            if puntos > mejor[0]:
                mejor = (puntos, a, b)
    _, a, b = mejor

    secciones, revisar, sin_ubicar = [], [], []
    for e, d in zip(entradas, debiles):
        pagina = estimar(a, b, e["pagina_impresa"])
        if not 0 <= pagina < n:
            revisar.append(f"'{e['titulo'][:50]}' cae fuera del PDF; se omitió.")
            continue
        if secciones and pagina <= secciones[-1]["pagina_impresa_inicio"]:
            revisar.append(f"'{e['titulo'][:50]}' empieza en la misma página que "
                           f"'{secciones[-1]['titulo'][:50]}'; se omitió.")
            continue
        if pagina not in d:
            sin_ubicar.append(f"{e['titulo'][:50]} (pág. {pagina})")
        secciones.append({
            "nivel": e["nivel"],
            "numero": e["numero"],
            "titulo": e["titulo"],
            "pagina_impresa_inicio": pagina,
            "_pagina_en_indice_impreso": e["pagina_impresa"],
        })
    if sin_ubicar:
        revisar.insert(0, f"{len(sin_ubicar)} de {len(entradas)} títulos no se encontraron "
                          "escritos en su página (portadillas en imagen o tipografía "
                          "decorativa); se usó la página que corresponde según el índice "
                          "impreso. Comprueba: " + "; ".join(sin_ubicar))
    if len(sin_ubicar) > len(secciones) / 2:
        revisar.insert(0, "Pocos títulos se pudieron confirmar en su página: la relación "
                          "entre página impresa y página del PDF puede estar mal; revisa "
                          "todas las páginas de inicio.")
    return secciones, revisar


# ----------------------------------------------------------------------------
# 3. Encabezado corrido
# ----------------------------------------------------------------------------

# Fracción mínima de páginas con texto cuya primera línea se repite en la
# página siguiente o anterior para considerar que hay encabezado corrido.
MIN_FRACCION_ENCABEZADO = 0.6
SEPARADORES_ENCABEZADO = (" — ", " | ", ": ")


def _desde_encabezado(textos):
    primeras = []
    for t in textos:
        lineas = [l.strip() for l in t.split("\n") if l.strip()]
        # Sin el número de página, vaya al final o al principio.
        primera = re.sub(r"^\d{1,4}\s+|\s+\d{1,4}$", "", lineas[0]) if lineas else ""
        # Rayas y guiones de separación mezclados ("A — B", "A – B", "A– B").
        primeras.append(re.sub(r"\s*[—–]\s*|\s+-\s+", " — ", primera))
    con_texto = [i for i, l in enumerate(primeras) if l]
    if len(con_texto) < 4:
        return []
    def fraccion_repetida(paso):
        return sum(
            1 for i in con_texto
            if (i >= paso and primeras[i - paso] == primeras[i])
            or (i + paso < len(primeras) and primeras[i + paso] == primeras[i])
        ) / len(con_texto)

    # paso 1: el mismo encabezado en páginas seguidas. paso 2: encabezado
    # alterno, típico de libros (página par con el título del libro, impar
    # con el del capítulo).
    paso = next((p for p in (1, 2) if fraccion_repetida(p) >= MIN_FRACCION_ENCABEZADO), None)
    if paso is None:
        return []

    conteo = Counter(primeras[i] for i in con_texto)
    # En el encabezado alterno, el que no cambia nunca (título del libro,
    # autor) no abre secciones.
    fijos = ({h for h, c in conteo.items() if c > 0.3 * len(con_texto)} if paso == 2 else set())
    encabezados = set(conteo) - fijos
    # Encabezados que duran al menos 2 páginas, en orden de primera aparición.
    inicios = {}
    for i in con_texto:
        h = primeras[i]
        if h in encabezados and conteo[h] >= 2 and h not in inicios:
            inicios[h] = i
    if len(inicios) < 2:
        return []

    # Prefijo común ("Manual X — ") que no forma parte del título.
    distintos = list(inicios)
    prefijo = os.path.commonprefix(distintos)
    corte = max(prefijo.rfind(sep) + len(sep) if sep in prefijo else 0
                for sep in SEPARADORES_ENCABEZADO)
    secciones = []
    for h, i in sorted(inicios.items(), key=lambda x: x[1]):
        # Si la página anterior no tiene texto o no trae ningún encabezado
        # corrido (portadilla, primera página del capítulo), la sección
        # empieza ahí.
        previa = primeras[i - 1] if i > 0 else None
        sin_encabezado = not previa or (paso == 2 and conteo[previa] == 1)
        inicio = i - 1 if i > 0 and sin_encabezado else i
        secciones.append({"nivel": 1, "numero": None, "titulo": h[corte:].strip() or h,
                          "pagina_impresa_inicio": inicio})
    if secciones[0]["pagina_impresa_inicio"] > 0:
        secciones[0]["pagina_impresa_inicio"] = 0
    return secciones


# ----------------------------------------------------------------------------

def generar(ruta_pdf, nivel_max=1):
    """Devuelve (indice, origen), con origen en {"marcadores", "tabla de
    contenido", "encabezado corrido", None}."""
    revisar = []
    with pdfplumber.open(ruta_pdf) as pdf:
        meta = pdf.metadata or {}
        secciones, origen = _desde_marcadores(pdf, nivel_max), "marcadores"
        textos = [p.extract_text() or "" for p in pdf.pages]
        textos_toc = [_texto_para_indice(p) for p in pdf.pages[:MAX_PAGINAS_TOC]]
        if secciones:
            # Los marcadores a veces omiten capítulos: si también hay índice
            # impreso, se avisa de las secciones que solo aparecen en él.
            del_toc, _ = _desde_toc(textos, textos_toc, nivel_max)
            paginas = {s["pagina_impresa_inicio"] for s in secciones}
            faltan = [f"{s['titulo'][:50]} (pág. {s['pagina_impresa_inicio']})"
                      for s in del_toc if s["pagina_impresa_inicio"] not in paginas]
            if faltan:
                revisar.append("El índice impreso trae secciones que no están en los "
                               "marcadores; añádelas si son contenido: " + "; ".join(faltan))
        else:
            secciones, revisar = _desde_toc(textos, textos_toc, nivel_max)
            origen = "tabla de contenido"
            if not secciones:
                secciones, origen = _desde_encabezado(textos), "encabezado corrido"
                if secciones:
                    revisar.append("Secciones deducidas del encabezado de página: confirma "
                                   "títulos y que ninguna sección quedó partida en dos.")
        if not secciones:
            origen = None

    titulo_doc = (meta.get("Title") or "").strip() or os.path.splitext(os.path.basename(ruta_pdf))[0]
    indice = {
        "titulo": titulo_doc,
        "_comentario_metadatos": "Los campos del front-matter se definen en metadatos.json "
                                 "(--metadatos). Aquí puedes añadir valores detectados para este "
                                 "documento (p. ej. tipo_documento, autor, fecha_publicacion) que "
                                 "llenarán los campos marcados como \"auto\".",
        "offset_pagina_impresa": 0,
        "_comentario_offset": f"offset 0: pagina_impresa_inicio es el índice 0-based de pdfplumber "
                              f"(generado desde: {origen or 'esqueleto'}).",
        "secciones": secciones or [
            {"nivel": 1, "numero": None, "titulo": "TODO [REVISAR] completar desde la tabla de contenido",
             "pagina_impresa_inicio": 0}
        ],
    }
    if revisar:
        indice["_revisar"] = revisar
    return indice, origen


def main():
    args = sys.argv[1:]
    nivel_max = 1
    if "--nivel-max" in args:
        i = args.index("--nivel-max")
        nivel_max = int(args[i + 1])
        args = args[:i] + args[i + 2:]
    if not args:
        print(__doc__)
        sys.exit(1)

    ruta_pdf = args[0]
    salida = args[1] if len(args) > 1 else os.path.splitext(ruta_pdf)[0] + ".indice.json"
    indice, origen = generar(ruta_pdf, nivel_max)
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(indice, f, ensure_ascii=False, indent=2)

    if origen:
        print(f"✅ Índice con {len(indice['secciones'])} secciones (desde {origen}): {salida}")
    else:
        print(f"⚠️  Sin marcadores, tabla de contenido ni encabezado corrido reconocibles. "
              f"Esqueleto escrito en {salida}: complétalo leyendo el documento "
              "(ver references/indice-json.md).")
    for nota in indice.get("_revisar", []):
        print(f"   · REVISAR: {nota}")
    print("   Revisa el título y las secciones antes de correr guias_tecnicas.py.")


if __name__ == "__main__":
    main()
