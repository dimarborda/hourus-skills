# Lecciones aprendidas

Patrones extraídos de análisis de plataformas y especificaciones reales que
sirvieron de base para esta skill. No son casos para replicar: son criterios
que separan una especificación construible de una lista de deseos. Léelos
antes de escribir `04` y `05`.

## Del análisis del referente

- **Encuentra el objeto central.** En una plataforma de venta de productos
  digitales es la transacción: de su estado dependen las comisiones, el
  acceso al contenido y la sincronización con terceros. Quien acierta el
  objeto central acierta el modelo de datos.
- **La API pública es el mejor plano del modelo de datos.** Los objetos y
  atributos que expone (y la carga útil de sus webhooks) son casi las tablas.
- **Las limitaciones del referente son oportunidades** (comisión alta,
  dependencia de un proveedor, plazos de pago largos…). Registrarlas evita
  copiar también sus defectos y da el diferenciador.
- **Lo que parece accesorio puede ser ingreso**: p. ej. la recuperación de
  pagos fallidos actúa directamente sobre la facturación. Mira qué cobra el
  referente además del núcleo.

## Del diseño propio

- **Un ciclo, no una lista de funciones.** Una buena plataforma se explica
  en 4-7 pasos que vuelven a empezar (p. ej. plan → tareas → estimación →
  ejecución → medición → reporte → plan). Si no puedes dibujar el ciclo,
  falta decidir D1.
- **Un rasgo distintivo frente al referente.** Copiar todo sin
  diferenciador produce un clon sin razón de existir. Escríbelo en una
  frase (p. ej. "ninguna tarea nace suelta: todas salen de un objetivo").
- **Etapa cero antes que nada.** Sin identidad, roles y bitácora, ninguna
  otra etapa es auditable.
- **Lo que mueve dinero o reputación va al final.** Incentivos, rankings,
  pagos y gamificación llegan cuando la medición ya es confiable; si no, se
  premian datos que nadie cree.
- **Criterios de salida observables** ("un usuario real completa el ciclo
  sin hojas de cálculo paralelas"), no "módulo terminado".
- **La columna "qué NO puede hacer"** de cada actor vale más que la de "qué
  hace": se convierte directamente en políticas RLS.
- **Los procesos automáticos y la IA son actores** con permisos y bitácora
  propios. La IA redacta, propone y detecta; nunca acepta, aprueba ni publica
  sin un humano registrado.
- **Nada calculado se digita a mano**: se calcula y se muestra la fórmula.
  Quien no reconoce un dato debe poder ver su traza.
- **Puntos acotados**: si un caso estima más de 13 puntos, todavía no se
  entiende; descomponlo antes de construirlo.

## De proyectos con plataforma existente

- **Nombres parecidos no son lo mismo.** Lo que una organización necesita
  no es lo mismo que lo que necesita un territorio o un mercado; un
  inventario vivo no es lo mismo que un documento adoptado y congelado.
  Mezclarlos rompe la lógica. Distínguelos por escrito antes de diseñar.
- **Reutilizar antes que duplicar**: dos maquinarias para lo mismo producen
  dos verdades. Tabla explícita de "ya existe / por construir".
- **Hay decisiones que no le tocan a la plataforma**: listarlas aparte
  ("lo que hay que decidir antes") evita codificar supuestos.

## De gobierno y confianza

- Cambios de estado con actor, fecha, versión y motivo; nada de cambios
  silenciosos.
- Operaciones financieras idempotentes y corregibles con ajustes, nunca con
  borrado.
- Métricas individuales: por defecto solo las ve la persona y su líder;
  rankings públicos solo si alguien con autoridad los activa.
- Un promedio alto con dispersión alta no es consenso: muestra la dispersión.
