# Perfiles de fuente

El motor solo quita ruido **genérico** (números de página, "Página N de M",
"Hoja N de M"). Lo que es propio de un portal, publicador o documento
concreto (su membrete, su pie de página, el título repetido en cada página,
su aviso legal) se describe en un perfil JSON y se activa con:

```bash
python3 SKILL_DIR/scripts/motor_normativo.py norma.pdf --perfil-fuente perfil.json
python3 SKILL_DIR/scripts/procesar_lote.py --perfil-fuente perfil.json [--perfil-fuente otro.json]
python3 SKILL_DIR/scripts/guias_tecnicas.py doc.pdf doc.indice.json --perfil-fuente perfil.json
```

La skill **no trae perfiles**: son propios de cada lote o cliente y viven
fuera de ella. `diagnosticar_pdf.py` revisa los de `perfiles-fuente/` en el
directorio de trabajo (cwd o `PDF_MD_WORKDIR`) y los de las carpetas listadas
en `PDF_MD_PERFILES` (separadas por `:`); si la `deteccion` de alguno
coincide con el PDF, sugiere pasarlo. Sin
perfil, el `.md` sale igual de estructurado, pero con ese ruido dentro del
texto.

## Formato

```json
{
  "nombre": "mi-portal",
  "descripcion": "Para qué fuente sirve y cuándo usarlo.",
  "lineas_ruido": ["^Mi Portal de Normas\\s*$", "^Documento \\d+ de \\d{4}.*Mi Portal\\s*$"],
  "bloques_ruido": [],
  "deteccion": "Mi\\s+Portal\\s+de\\s+Normas",
  "fuente": "Mi Portal de Normas",
  "nota_final": "Texto legal que el publicador pide incluir (opcional)."
}
```

| Campo | Qué hace |
|---|---|
| `lineas_ruido` | Regex (sin distinguir mayúsculas) contra cada línea ya recortada; si coincide desde el inicio, la línea se elimina. Ánclalas con `^…$` para no borrar menciones reales en el cuerpo. |
| `bloques_ruido` | Regex sobre el texto completo, antes de partir en líneas, para ruido de varias líneas (p. ej. un pie que corta el título y deja el resto en la línea siguiente). Se reemplaza por un salto de línea. |
| `deteccion` | Regex que reconoce la fuente en el texto. Si coincide, rellena `fuente` y `nota_final`, y `diagnosticar_pdf.py` sugiere el perfil. |
| `fuente` | Valor del campo `fuente` (solo si `metadatos.json` lo deja en `"auto"`). |
| `nota_final` | Si existe, se añade al final del `.md` como "**Nota de la fuente:** …". |

Todos los campos son opcionales. Las claves que empiezan por `_` se ignoran
(sirven de comentario).

## Crear uno nuevo

1. Convierte un PDF de muestra sin perfil y busca en el `.md` las líneas que
   se repiten en cada chunk (`sort | uniq -c | sort -rn` sobre el cuerpo).
2. Escribe una regex anclada por cada una en `lineas_ruido`; prueba que no
   coincida con texto real del cuerpo.
3. Vuelve a convertir con `--perfil-fuente` y compara el número de chunks y
   los encabezados de CAPÍTULO/SECCIÓN.
4. Guárdalo en `<trabajo>/perfiles-fuente/` (o en una carpeta compartida
   que apuntes con `PDF_MD_PERFILES`), nunca dentro de la skill. Ningún
   perfil se aplica por defecto.
