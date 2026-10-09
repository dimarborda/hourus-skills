---
name: pdf-a-markdown
description: Convierte PDF a Markdown estructurado y listo para RAG (front-matter YAML con metadatos definidos por el usuario, jerarquía de encabezados, breadcrumb **Ruta:** y marcas <!-- CHUNK -->). Primero diagnostica cada PDF y elige la ruta correcta — norma articulada (ley/decreto/resolución con ARTÍCULO N), guía/manual/informe por secciones (incluido diseño a 2-3 columnas y pliegos dobles), PDF escaneado (OCR) o tablas con grilla real — y luego valida la salida. Úsala siempre que alguien pida "convertir/pasar/estructurar un PDF a markdown", "procesar PDFs", "preparar documentos para el RAG / base de conocimiento", "sacar el texto de un PDF", "extraer tablas de un PDF", "hacer OCR", o deje PDF nuevos en una carpeta para convertir, aunque no mencione Markdown ni RAG explícitamente.
---

# PDF → Markdown estructurado (RAG-ready)

Empaqueta un pipeline de conversión probado con lotes reales de normas y
guías técnicas, y lo deja reutilizable para cualquier PDF. El núcleo no
depende de ningún país, portal ni organización: lo propio de una fuente
concreta (membretes, pies de página, notas legales) se activa solo con un
**perfil de fuente** opcional (§3).

Todo es **determinístico** (pdfplumber + reglas, sin LLM ni internet). Tu
trabajo como agente es: diagnosticar, elegir la ruta, correr el script
correcto, **revisar** la salida y reportar lo que quedó pendiente. No
reescribas el parseo a mano ni "resumas" contenido: la salida debe ser
verbatim del PDF.

**RAG o solo conversión:** por defecto el `.md` lleva las marcas para RAG
(`<!-- CHUNK … -->` y `**Ruta:** …`). Si el usuario solo quiere convertir el
PDF (leerlo, editarlo, pasarlo a otra herramienta), añade `--sin-chunks` a
`motor_normativo.py`, `procesar_lote.py` o `guias_tecnicas.py`: queda
front-matter + encabezados + texto, con las palabras cortadas por guion
unidas y las líneas de una misma oración juntas. Si no lo dice, asume RAG.

**Mínima fricción para el usuario:** nunca le pidas que escriba
`metadatos.json` ni el índice JSON de una guía. Los generas tú, los revisas
y en el reporte le dices qué decidiste; él solo corrige si algo no le sirve.

`SKILL_DIR` = carpeta de este archivo. Los scripts viven en `SKILL_DIR/scripts/`.

## 0. Preparar entorno (una vez)

```bash
pip install -r SKILL_DIR/requirements.txt        # pdfplumber
```

Solo si hay PDF escaneados (ruta OCR):

```bash
brew install tesseract tesseract-lang ghostscript qpdf unpaper
pip install ocrmypdf
```

Si Homebrew falla por permisos/links, díselo al usuario; no uses `sudo`.

## 1. Diagnosticar SIEMPRE antes de convertir

```bash
python3 SKILL_DIR/scripts/diagnosticar_pdf.py archivo.pdf      # o una carpeta
```

Mide texto, `ARTÍCULO N`, índice/marcadores, columnas, pliegos, tablas,
`(cid:N)` y perfiles de fuente que coinciden, y recomienda una **RUTA**:

| RUTA | Qué es | Ir a |
|---|---|---|
| `normativo` | Ley, decreto, resolución, circular: texto con `ARTÍCULO N` | §3 |
| `guia-por-secciones` | Guía, manual, informe, reglamento técnico, libro: estructura por índice | §4 |
| `ocr` | Escaneo sin texto seleccionable | §5, luego volver a diagnosticar |
| `revisar-manual` | Dañado / cifrado / protegido | Reportar al usuario |

Las notas adicionales (tablas, columnas, cid) aplican **encima** de la ruta:
ver §6 y §7. La recomendación es una heurística: si al mirar el PDF ves otra
cosa, manda tu criterio (y dilo en el reporte).

## 2. Metadatos del front-matter (sin frenar la conversión)

El front-matter YAML **no tiene campos fijos**, pero cambiarlo después no
obliga a reconvertir, así que **no detengas la conversión para preguntar**:

1. **Escribe tú `metadatos.json`** en el directorio de trabajo:
   - Si el usuario ya dijo para qué son los `.md` (cliente, campos, filtros
     del RAG, idioma…), refléjalo.
   - Si no, usa el perfil según la ruta: `normativo` si todo el lote son
     normas, `general` en otro caso:
     `python3 SKILL_DIR/scripts/metadatos.py plantilla normativo > metadatos.json`.
   - Solo haz **una** pregunta corta antes si el lote es grande (más de ~20
     PDF) y no hay ninguna pista del uso. Si responde "como sea", sigue con el
     perfil por defecto.

   Valores: `"auto"` = lo detecta el conversor · `null` = pendiente
   (`TODO [REVISAR]`) · `false` = omitir · cualquier otro = literal.
   `"documentos": {"x.pdf": {...}}` permite valores por archivo. Ejemplo:
   [assets/metadatos.ejemplo.json](assets/metadatos.ejemplo.json); campos de
   cada perfil: `python3 SKILL_DIR/scripts/metadatos.py perfiles`.
2. Pásalo a cualquier conversor con `--metadatos metadatos.json` (campos
   detectables: [references/formato-salida.md](references/formato-salida.md)).
3. **En el reporte** (§8) muestra los campos que quedaron y los `TODO`, y
   ofrece ajustarlos. Si el usuario cambia algo, edita `metadatos.json` y
   aplícalo sin reconvertir:
   `python3 SKILL_DIR/scripts/metadatos.py aplicar doc.md metadatos.json [--pdf doc.pdf]`.

## 3. Ruta `normativo` — motor por artículos

**Un archivo suelto** (no mueve nada):

```bash
python3 SKILL_DIR/scripts/motor_normativo.py norma.pdf [salida.md] --metadatos metadatos.json
python3 SKILL_DIR/scripts/motor_normativo.py carpeta_pdfs/ carpeta_md/ --metadatos metadatos.json
```

**Flujo de lote con carpetas** (cuando el equipo deja PDF en una cola). Se
ejecuta desde el directorio de trabajo (o con `PDF_MD_WORKDIR=/ruta`):

```
<trabajo>/
├── PDF/No procesados/     ← entrada
├── PDF/Procesados/        ← éxito (se mueve el PDF)
├── PDF/Requiere-revision/ ← fallo + NOTAS.md con motivo y sugerencia
└── md/                    ← un .md por PDF
```

```bash
cd <trabajo> && python3 SKILL_DIR/scripts/procesar_lote.py --metadatos metadatos.json
```

Ignora `.DS_Store` y locks `.~lock.*#` (alguien tiene el PDF abierto: avisa).
Un PDF sin artículos reconocidos va a `Requiere-revision/` **sin** generar
`.md` (un .md sin chunks útiles solo ensucia `md/`).

**Perfiles de fuente** (`--perfil-fuente perfil.json`, repetible, en los tres
conversores): membrete/pie de un portal o publicador concreto, cómo
reconocerlo para rellenar `fuente` y una nota legal opcional. Úsalo solo si
el diagnóstico lo sugiere o el usuario lo pide; para un membrete nuevo, crea
un perfil en vez de tocar el código: [references/perfiles-fuente.md](references/perfiles-fuente.md).

Reconoce `LIBRO > PARTE > TÍTULO > CAPÍTULO > SECCIÓN > SUBSECCIÓN > ARTÍCULO > PARÁGRAFO`,
metadatos (tipo, número, año, objeto, fecha, firmante) y subdivide artículos
largos (`MAX_CHUNK_CHARS = 3500`) sin cortar numerales. Si un documento usa
otra numeración ("Artículo Primero.-"), ajusta `HIERARCHY_PATTERNS` en
`motor_normativo.py` — no escribas un parser paralelo.

## 4. Ruta `guia-por-secciones` — guías, manuales, informes y libros

Sin marcadores de estructura regulares, `guias_tecnicas.py` recibe las
secciones en un índice JSON y automatiza lo demás (columnas, limpieza, chunks).

1. **Generar el índice** (siempre con el script; no lo escribas desde cero):
   ```bash
   python3 SKILL_DIR/scripts/generar_indice.py doc.pdf          # -> doc.indice.json
   ```
   Prueba en orden: marcadores del PDF, tabla de contenido impresa (con o sin
   puntos guía, también a dos columnas y en pliegos dobles) y encabezado
   corrido (también el alterno de los libros). Deja páginas 0-based
   (`offset_pagina_impresa: 0`): no hay que calcular ningún desfase.
2. **Revisar el borrador tú mismo** antes de convertir:
   - Lee `_revisar`: para cada página dudosa, mira el texto de esa página
     (o renderízala) y corrige `pagina_impresa_inicio`.
   - Pasa a mayúscula inicial los títulos que vienen en MAYÚSCULAS del índice
     impreso, respetando siglas.
   - Quita entradas que no son contenido (portada, "Contenido", "Siglas") y
     subsecciones que se colaron como nivel 1.
   - Si el script solo pudo escribir un esqueleto, arma tú el índice leyendo
     el documento: **[references/indice-json.md](references/indice-json.md)**.

   Los campos extra del índice (`autor`, `fecha_publicacion`…) alimentan los
   campos `"auto"` de `metadatos.json`.
3. **Convertir:**
   ```bash
   cd <trabajo> && python3 SKILL_DIR/scripts/guias_tecnicas.py doc.pdf doc.indice.json --metadatos metadatos.json
   ```
   Escribe `<trabajo>/md/doc.md`. Solo mueve el PDF si está dentro de
   `<trabajo>/PDF/` (flujo de lote); un PDF suelto se queda donde está.

Quita los encabezados/pies repetidos en el borde de 3+ páginas (título del
libro, autor, capítulo) y detecta columnas y pliegos (> 800 pt). Si el orden
de lectura sale mezclado, ajusta `ANCHO_BIN_PT` / `HUECO_MINIMO_PT` /
`DENSIDAD_MINIMA` — ver [references/lecciones-aprendidas.md](references/lecciones-aprendidas.md).

## 5. Ruta `ocr` — escaneos

**No apliques OCR a ciegas.** Antes, mira la primera página (renderízala a
imagen): en un caso real, un "PDF sin texto" resultó ser un póster mal
catalogado, no un escaneo. Si es un escaneo real:

```bash
cd <trabajo> && python3 SKILL_DIR/scripts/ocr_lote.py nombre.pdf   # busca en PDF/Requiere-revision/
```

Corre `ocrmypdf --language spa+eng --deskew --clean --optimize 1` (otro
idioma: `PDF_MD_OCR_LANG`, p. ej. `por`, `fra+eng`), verifica que haya texto y
mueve el PDF a `PDF/No procesados/`. Para un archivo suelto, usa `ocrmypdf`
con esos flags y vuelve a §1. Si el OCR sale ilegible (firmantes, fechas o
tablas corruptas), busca una versión en texto del mismo documento (portal
oficial en HTML, otra edición) antes de insistir.

## 6. Tablas con grilla real

Ni el motor normativo ni la detección de columnas entienden tablas: las
convierten en texto con columnas pegadas o mezclan filas. Para las páginas
que el diagnóstico marcó con tablas:

```bash
python3 SKILL_DIR/scripts/extraer_tablas_pdf.py doc.pdf PAG_INI PAG_FIN   # índices 0-based, inclusivos
```

Fusiona tablas que continúan en la página siguiente y devuelve Markdown.
**Verifica fila por fila** contra `page.extract_text()`: `extract_tables()`
puede omitir filas sin avisar (caso real: 49 filas extraídas de 63). Luego
reemplaza en el `.md` el tramo garabateado por la tabla, dentro del mismo
chunk. Si ya tienes los datos (CSV/JSON/texto a columnas):

```bash
python3 SKILL_DIR/scripts/formatear_tablas.py datos.csv -o tabla.md
```

Celdas vacías (tabla dibujada o en imagen): transcribe mirando la página.

## 7. Post-proceso y control de calidad

1. **Ecuaciones/símbolos** (`(cid:N)` en la salida):
   `python3 SKILL_DIR/scripts/corregir_ecuaciones.py doc.md` — `CID_MAP` se
   calibró con la tipografía de un documento técnico concreto; verifica una
   muestra contra el PDF antes de confiar en él para otro documento.
2. **Limpieza y estructura** (pies/encabezados repetidos, llamadas a nota,
   viñetas, jerarquía de títulos, incisos indentados): aplica las reglas de
   **[references/limpieza-y-estructura.md](references/limpieza-y-estructura.md)**.
3. **Checklist antes de dar por bueno un `.md`:**
   - [ ] Front-matter con los campos acordados; `TODO [REVISAR]` contados (y completados si el usuario lo pide, leyendo el propio texto).
   - [ ] (Salvo `--sin-chunks`) toda unidad de contenido dentro de `<!-- CHUNK id=… ruta=… -->` … `<!-- /CHUNK -->`, ids únicos.
   - [ ] Leíste al menos una sección completa: no hay frases de columnas distintas pegadas en la misma línea.
   - [ ] Tablas verificadas fila por fila (§6).
   - [ ] Ningún chunk dice `[REVISAR: … vacío]` sin explicación (página gráfica, anexo en imagen…).
   - [ ] Sin texto inventado, resumido ni reordenado respecto al PDF.

El formato de salida completo está en **[references/formato-salida.md](references/formato-salida.md)**.

## 8. Reporte al usuario

Por cada PDF: ruta usada, `.md` generado (ruta del archivo), nº de chunks,
campos de metadatos que quedaron en `TODO [REVISAR]` (por nombre), lo que
decidiste por tu cuenta (perfil de metadatos, secciones del índice y cómo
las verificaste) y lo que quedó fuera o requiere decisión humana (PDF en
`Requiere-revision/` con su motivo, tablas en imagen, páginas gráficas).
Ofrece completar los `TODO` leyendo el texto si aplica.

## Límites conocidos

- El motor normativo reconoce normas **en español** con la estructura
  habitual ("DECRETO/LEY/RESOLUCIÓN N DE AÑO", "Por el/la cual…",
  `ARTÍCULO N`, fórmulas de cierre y firmas). Con otras convenciones la
  jerarquía funciona, pero los campos `"auto"` pueden quedar en `TODO
  [REVISAR]`; ajusta `HIERARCHY_PATTERNS` o `TIPO_NORMA_PATTERNS`. Con un
  OCR malo el título detectado puede ser erróneo: revísalo siempre.
- `guias_tecnicas.py` hace un chunk por sección de primer nivel; no detecta
  subtítulos internos (requeriría analizar tamaños de fuente).
- Las tablas dentro de normas no se integran automáticamente (§6 es manual).
- No hay OCR de imágenes incrustadas en PDF con texto.
