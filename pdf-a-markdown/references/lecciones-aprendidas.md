# Lecciones aprendidas

Casos reales que costaron tiempo y que explican por qué los scripts son como
son. Léelo cuando una conversión salga rara antes de "arreglar" un script.

## Diagnóstico

- **No todo PDF sin texto es un escaneo.** Un supuesto "guía sin texto"
  resultó ser un póster/mapa de una sola página mal catalogado. OCR no lo habría salvado.
  Mira la primera página antes de decidir.
- **"No se reconoció ningún ARTÍCULO" no siempre es un bug del patrón**: muchas
  veces el documento es una guía/manual y debe ir por `guias_tecnicas.py`.

## Metadatos del motor normativo

- El tipo/número/año/objeto se buscan solo en los primeros 2500 caracteres
  (`HEADER_WINDOW_CHARS`) y se toma el match más temprano: las leyes largas
  citan otras normas ("…artículo 173 de la Ley 100 de 1993…") y esas citas
  contaminaban el título y el breadcrumb de todos los chunks.
- Ruido de extracción entre palabra clave y número
  ("RESOLUCIÓN NÚMERO O 011 1234(cid:9) DE 2021") ya se tolera; si aparece
  uno nuevo, ajusta `_NUM_DE_ANIO` o `TIPO_NORMA_PATTERNS`.
- `modifica`/`deroga`/`firmante` requieren criterio jurídico: quedan en
  `TODO [REVISAR]` a propósito. Se completan leyendo el Artículo 1 y las
  disposiciones finales.

## Columnas

- **Cortar la página en franjas de ancho igual no funciona**: las columnas
  reales casi nunca ocupan el ancho completo (imágenes, íconos, márgenes
  variables) y el corte partía columnas por la mitad, produciendo líneas como
  "...normatizada procesos – objetivos que pe...". Por eso `detectar_columnas`
  mide los huecos verticales reales entre palabras.
- **Ampliar el recorte (solapamiento) empeora el resultado**: arrastra texto
  de la columna vecina. Los fragmentos de 1-2 letras que deja el título
  decorativo de cada sección se descartan como ruido (el título real viene del índice).
- Señal de fallo: dos frases sin relación pegadas en la misma línea. Ajusta
  `ANCHO_BIN_PT` (4), `HUECO_MINIMO_PT` (14), `DENSIDAD_MINIMA` (12) en
  `guias_tecnicas.py`; no hace falta tocar el índice.
- Página con muy poco texto en una columna (< `DENSIDAD_MINIMA` palabras) →
  esa columna se descarta entera. Revisa visualmente antes de culpar al script.

## Tablas

- Una tabla real tratada como columnas de prosa sale como palabras cortadas
  sin relación (concatena cada columna de arriba abajo en vez de fila por fila).
  Confirma con `page.extract_tables()` y usa `extraer_tablas_pdf.py`.
- **`extract_tables()` omite filas en silencio**, sobre todo la última antes
  de un salto de página o de la leyenda "Tabla N° / Fuente:". Caso real: 49
  filas extraídas, 63 reales (faltaban grupos de filas completos). Verificación
  obligatoria contra `page.extract_text()`.
- En normas, `extract_text()` pega las columnas de una tabla
  (`74740947.09105423.95Punto 74`); el motor normativo no integra tablas
  todavía, así que se reemplazan a mano dentro del chunk.

## OCR y fuentes alternativas

- OCR de un mal escaneo puede dejar firmante, fecha y tablas inservibles
  (caso real: una resolución escaneada). Antes de insistir, busca el mismo documento
  como texto/HTML en un portal oficial y conviértelo desde ahí.
- Tablas incrustadas como imagen no se recuperan con ninguna de estas
  herramientas: se transcriben a mano mirando la imagen.

## Ecuaciones

- Fuentes de símbolos producen `(cid:N)`. El mapeo a LaTeX de
  `corregir_ecuaciones.py` es específico de la fuente del documento original:
  valida una muestra antes de aplicarlo a otro PDF y amplía `CID_MAP` si hace falta.

## Paginación de índices

- Numeración impresa con saltos (páginas divisorias sin número) → usar
  `offset 0` e índices 0-based de pdfplumber directamente, no varios offsets.

## Ruido propio de una fuente

- Cada portal o publicador repite su membrete, su pie ("<Norma> N de AAAA ·
  pág. · nombre del portal") o el título del documento en cada página. Sin
  limpiarlo, ese texto se cuela en casi todos los chunks y en los nombres de
  CAPÍTULO/SECCIÓN que caen en un salto de página. Ponerlo en el código ataba
  el motor a esas fuentes; por eso vive en perfiles JSON (`--perfil-fuente`,
  ver [perfiles-fuente.md](perfiles-fuente.md)) y `diagnosticar_pdf.py`
  sugiere el perfil cuando su `deteccion` coincide.
