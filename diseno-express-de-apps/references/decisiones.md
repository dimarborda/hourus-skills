# Las cinco decisiones

Las decisiones se toman **antes** de investigar a fondo y antes de escribir
código. Son pocas a propósito: cada una cierra un frente completo y permite
avanzar rápido. Se registran en `docs/00-decisiones.md` con su porqué.

Regla de conducción: el usuario aporta la intención; tú aportas las
opciones. Nunca le preguntes "¿qué referente quieres?" en abierto: propón
2-3 con una recomendada y la razón.

---

## D1 · Qué quiero construir

Objetivo: una frase que cualquiera entienda.

> **[Plataforma] para que [usuario] pueda [resultado], sin [dolor actual].**

Preguntas guía (elige las que falten, no todas):
- ¿Quién la usa todos los días? ¿Quién paga? (pueden ser distintos)
- ¿Qué hace hoy esa persona sin la plataforma? (Excel, WhatsApp, papel…)
- ¿Qué tiene que poder hacer en la primera versión para que valga la pena?
- ¿Es para uso interno, para clientes o para vender a otras organizaciones?
- ¿Cómo sabremos que funcionó? (un número observable)

Salida: enunciado, usuarios (máx. 5 roles), resultado medible, alcance
inicial (interno / clientes / producto).

Señales de alerta: más de 5 roles en la primera versión, "y también
debería…" repetido, ningún resultado medible → recorta antes de seguir.

## D2 · Basado en qué (referente funcional)

Objetivo: encontrar quién ya resolvió el mismo **problema estructural**,
aunque sea en otra industria.

Cómo buscar:
1. Reduce D1 a su mecánica: ¿es un marketplace de dos/tres lados? ¿un
   tablero de flujo de trabajo? ¿un catálogo con pagos? ¿una red de
   matching? ¿un sistema de reservas? ¿un ciclo de convocatoria-selección?
2. Busca la plataforma líder en esa mecánica (no en la industria):
   - Vender conocimiento/contenido digital → Hotmart, Teachable, Gumroad.
   - Gestionar trabajo en equipo → Trello, Jira, Linear, Asana.
   - Conectar demanda con oferta → Airbnb, Upwork, Fiverr, Uber.
   - Innovación abierta / retos → InnoCentive, HeroX, Kaggle.
   - Reservas y agenda → Calendly, Booksy, OpenTable.
   - Comunidad con membresía → Circle, Skool, Discord.
   - Formularios y trámites → Typeform, Jotform; gobierno: portales de trámites.
3. Combina si hace falta: **1 principal** (de donde sale el modelo de datos
   y el ciclo) + **0-2 secundarios** (una funcionalidad puntual cada uno).
   Ej.: gestor de tareas para equipos = Trello/Jira (tablero y flujo) +
   planning poker (estimación) + rachas e insignias tipo Duolingo.

Salida: tabla `referente | qué tomamos | qué NO tomamos`.

## D3 · Qué diseño visual quiero aplicar

Objetivo: describir la sensación con palabras concretas, no "bonito y moderno".

Ejes a decidir (propón valores):
- **Densidad**: aireado (consumidor) ↔ denso (herramienta de trabajo).
- **Tono**: sobrio/institucional ↔ cálido/cercano ↔ lúdico.
- **Plataforma principal**: escritorio, móvil o ambos (¿quién la usa en
  campo, quién en oficina?).
- **Modo**: claro, oscuro o ambos.
- **Identidad**: ¿hay marca existente (logo, colores) que respetar?
- **Accesibilidad / conectividad**: usuarios rurales, bajo ancho de banda,
  lenguaje claro (típico en proyectos públicos o territoriales).

## D4 · Basado en qué (referente visual)

Puede ser distinto del funcional: se puede tener la lógica de un
marketplace con la estética de Linear. Propón 2-3 productos cuya interfaz encarne D3 y que
el usuario pueda abrir para mirar. Si hay un sistema de diseño público
(Material, shadcn/ui, Radix, Tailwind UI) que se acerque, dilo: acelera.

Salida: referente visual + 3-5 rasgos concretos a tomar ("barra lateral
colapsable", "tarjetas con borde fino y sin sombra", "tipografía grande en
números clave", "estados vacíos ilustrados").

## D5 · Qué modelo de negocio puedo obtener

Objetivo: copiar cómo gana dinero el referente y ajustarlo al contexto.

Patrones frecuentes (identifica el del referente y propón el adaptado):

| Patrón | Cómo cobra | Ejemplo | Implicación técnica |
|---|---|---|---|
| Comisión por transacción (take rate) | % + fijo por venta aprobada | Etsy, Hotmart, Uber | Pasarela con split de pagos; la transacción es el objeto central |
| Suscripción SaaS por puesto o plan | Mensual/anual | Jira, Notion | Planes, límites por plan, multiempresa (tenant) |
| Freemium | Gratis con límites, pago por más | Trello | Medir uso y bloquear al pasar el límite |
| Marketplace con comisión a ambos lados | Fee comprador + vendedor | Airbnb | Reservas, disputas, reputación |
| Escalonado por volumen | % baja al crecer el cliente | Pasarelas de pago, plataformas de creadores | Diseñarlo desde el inicio: retiene clientes |
| Servicios de valor agregado | Herramientas extra aparte del núcleo | Shopify (apps, temas) | Catálogo de add-ons |
| Financiero (anticipos, float) | Cobra por adelantar pagos | Shopify Capital, anticipos a vendedores | Regulado: evitar en MVP |
| Licencia institucional / contrato | Pago fijo de una entidad | Plataformas para gobierno | Sin pasarela; foco en reportes y trazabilidad |
| Uso interno (sin ingreso directo) | Ahorro / productividad | Herramientas internas | Dejar preparado el paso a SaaS (multiempresa) |
| Participación / regalías | % de ingresos futuros de lo creado | Plataformas de innovación abierta | Libro mayor de contribuciones, conciliación |

Preguntas guía:
- ¿Quién recibe el valor y quién paga? ¿Cuándo paga (antes, por uso, al
  éxito)?
- ¿Cuál es la variable que alinea nuestro ingreso con el del cliente?
  (En una plataforma de comisión: la venta aprobada.)
- ¿Qué cobra el referente que aquí no aplica, y qué podríamos cobrar que él
  no cobra?
- ¿Qué parte del modelo **no** va en la primera versión? (Normalmente:
  todo lo que mueva dinero va en una etapa posterior a "operar el ciclo".)

Salida: modelo elegido, precio inicial tentativo, variable de alineación,
qué entra al MVP y qué se pospone, riesgos (regulación, fraude, impuestos).

---

## Formato del registro

Cada decisión en `00-decisiones.md` termina con:

```
**Por qué:** …
**Estado:** propuesta | aprobada
```

`expres.py validar` falla si alguna decisión no está `aprobada` o conserva
`TODO`.
