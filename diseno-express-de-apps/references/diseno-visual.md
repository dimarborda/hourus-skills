# Diseño visual a partir de un referente

Se copian **patrones de interfaz** (que no son protegibles y el usuario ya
conoce), no la identidad gráfica. El resultado es `docs/03-diseno-visual.md`,
que Claude Code usa para generar pantallas coherentes sin un diseñador.

## Cómo observar el referente

Si hay navegador disponible, abre las páginas públicas del referente visual
(landing, precios, demo, capturas en tiendas de apps, galerías tipo
Mobbin/Dribbble del producto). Si no, pide al usuario 3-5 capturas.
Anota, no descargues assets.

Qué extraer:
- **Estructura de navegación**: barra lateral, barra superior, pestañas
  inferiores en móvil; cuántos niveles.
- **Pantallas arquetipo**: tablero/resumen, listado con filtros, detalle,
  formulario largo por pasos, tablero kanban, calendario, checkout, vacío.
- **Densidad y ritmo**: espaciado, tamaño de texto base, cuántos datos por fila.
- **Componentes distintivos**: tarjetas, chips de estado, tablas, avatares,
  barras de progreso, celebraciones.
- **Tono de los textos**: tuteo/usted, frases cortas, microcopias de error.
- **Estados**: vacío, cargando, error, éxito.

## Traducción a tokens propios

Base técnica fija: **Tailwind CSS + shadcn/ui** (componentes accesibles que
se copian al proyecto y se personalizan). Define en el documento:

```
Color primario:    <hex propio>   (no el del referente)
Neutros:           escala zinc | slate | stone
Acento / éxito / alerta / error: <hex>
Tipografía:        <Google Font>  (p. ej. Inter, Geist, Manrope, Source Sans 3)
Radio:             0.25rem | 0.5rem | 0.75rem
Densidad:          compacta | normal | amplia
Modo oscuro:       sí | no
```

Estos valores van a las variables CSS de shadcn (`--primary`, `--radius`…)
en `app/globals.css`.

## Inventario de pantallas

Tabla en el documento: `pantalla | rol | arquetipo del referente | casos de
uso que cubre | etapa`. Cada pantalla debe estar justificada por al menos un
caso de uso de `05-casos-de-uso.md`; pantallas sin caso se descartan.

## Reglas

- Nombre, logo, paleta, ilustraciones y textos **propios**. Si el usuario
  no tiene logo, usa el nombre en texto con la tipografía elegida.
- Mobile-first si algún rol trabaja en campo o desde el celular.
- Accesibilidad: contraste AA, foco visible, etiquetas en formularios.
- Lenguaje claro en español; prepara i18n solo si D1 lo exige.
