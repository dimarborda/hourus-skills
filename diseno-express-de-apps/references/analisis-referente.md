# Diseccionar el referente

Se producen dos documentos: un **análisis conceptual** del referente y un
**catálogo de sus casos de uso**. El objetivo no es describir el referente
por curiosidad, sino extraer el **vocabulario mínimo para construir algo
equivalente**.

## Fuentes (solo públicas)

En este orden, de más a menos confiable:
1. Sitio oficial: páginas de producto, **precios/tarifas**, funcionalidades.
2. Centro de ayuda / documentación de usuario (revela flujos reales y
   estados: "pendiente", "reembolsado", "vencida").
3. Portal de desarrolladores / API / webhooks: es la mejor fuente para el
   **modelo de datos** (los objetos y atributos de la API son las tablas).
4. Reseñas de usuarios (G2, Capterra, tiendas de apps): limitaciones reales.
5. Prensa y anuncios recientes (lanzamientos, IA).

Usa búsqueda web y el navegador. No inicies sesión en el referente ni uses
cuentas del usuario sin pedirlo. No hagas scraping masivo.

## `01-referente-conceptual.md` — secciones

1. **Ficha**: origen, categoría, cobertura, escala declarada, canales.
2. **Familias de producto**: cómo organiza su oferta (suele mapear las
   etapas del negocio de su cliente).
3. **Problema estructural**: tabla `obstáculo | manifestación concreta`.
4. **Propuesta de valor**: un enunciado + 2-3 decisiones de diseño que la
   sostienen (p. ej. en una plataforma de venta de cursos: cero
   costo de entrada, pagos propios, red de afiliados).
5. **Modelo de negocio**: lados del mercado (qué aporta / qué recibe cada
   uno), estructura de ingresos con cifras declaradas, ingresos
   complementarios, lógica económica (qué variable alinea los ingresos).
6. **Actores y roles**: `actor | definición | capacidades`.
7. **Dominios funcionales**: 4-8 dominios, cada uno con la pregunta que
   responde y su objeto central.
8. **Objetos de dominio**: `objeto | descripción | atributos` y relaciones
   estructurales (cardinalidades, qué estado gobierna a qué).
9. **Ciclo de vida** del objeto principal: etapas, qué ocurre, dominio.
10. **Capa de IA** (si existe).
11. **Seguridad, confianza y cumplimiento**.
12. **Diferenciadores** y **limitaciones** (de reseñas).
13. **Lecturas aplicables a nuestro proyecto** ← la sección más importante:
    5-8 conclusiones accionables ("el objeto central es la transacción
    porque de su estado depende el acceso y las comisiones").
14. Glosario y fuentes con fecha de consulta.

## `02-referente-casos-de-uso.md` — formato

- Actores con sigla de 3 letras (`PRO`, `COM`, `SIS`…). `SIS` = procesos
  automáticos del sistema.
- Mapa de módulos `MNN | denominación | nº casos`.
- Por módulo, tabla:

```
| Código | Caso de uso | Actor | Resultado esperado |
|---|---|---|---|
| CU-04-01 | Crear una oferta con precio y moneda | PRO | Condición comercial publicable |
```

- Verbo en infinitivo + objeto; resultado = estado verificable, no acción.
- Al final: **integraciones** (`categoría | plataformas | para qué`),
  eventos/webhooks si existen, y **frentes de complejidad para una
  implementación análoga** (`frente | complejidad | recomendación`).

Tamaño: 40-60 casos alcanzan para un MVP; 100+ para un análisis completo.
Prioriza los módulos del ciclo principal.

## Reglas

- Las cifras son "declaradas por la plataforma a <fecha>", no verificadas.
- Marca el documento como *análisis externo a partir de información
  pública; no es documentación oficial de <referente>*.
- No copies textos largos del referente: resume con palabras propias.
