# Feature: dibujar y editar como un CAD

Objetivo: que dibujar una sección se sienta como dibujar en un CAD — el comando se arma y se
desactiva, cancelar no destruye trabajo, se selecciona lo dibujado y las herramientas de edición
básicas actúan sobre el contorno.

Referencias: `odd/tasks/sectionlab-dimension-tool.md` (cotas, guías, enganches, cinta) sigue
vigente; esto lo complementa.

## Specs

- **S1 Un clic en vacío no dibuja ni borra.** El botón izquierdo sobre el vacío solo deselecciona.
  Dibujar exige armar el comando: el botón Dibujar, `L`, o `Enter` que repite el último comando.
  Hoy un clic perdido en el vacío ejecuta `begin_drawing()`, que reemplaza la sección por una
  vacía: se pierde el trabajo por apuntar mal. Quoted: «que paso con la opcion de dasactivar el
  comando de dibujar? por ejemplo para releccionar? me hace falta eso».
- **S2 Esc desactiva el comando y conserva lo trazado.** `Esc` termina el comando Dibujar dejando
  los vértices ya puestos como contorno abierto (seleccionable, editable, sin calcular hasta
  cerrarse). `Esc` con el comando Acotar activo lo desactiva igual que hoy. `Esc` sin comando
  limpia la selección. Quoted: «debemos poner un sistema para desactivar los comando activos …
  con esc». Corrige `cancel_drawing`, que hoy vacía la sección.
- **S3 Selección múltiple y por ventana.** `Ctrl+A` selecciona todos los vértices del contorno; un
  arrastre con el botón izquierdo sobre el vacío abre una ventana: de izquierda a derecha toma los
  vértices que quedan dentro, de derecha a izquierda los que toca o cruza (como un CAD). `Supr`
  borra los vértices seleccionados, o la cota seleccionada. Quoted: «seleccionar el dibujo
  completo y demas».
- **S4 Edición del contorno.** Cuatro operaciones sobre el contorno, cada una con su resultado
  medible en área e inercia:
  - **Chaflán** de un vértice a una distancia dada: lo sustituye por dos vértices sobre sus lados.
  - **Desplazamiento (offset)**: un contorno paralelo a una distancia, hacia dentro o hacia fuera;
    es cómo se hace un hueco con espesor. Se rechaza si el resultado se cruza consigo mismo, en
    vez de guardar geometría rota.
  - **Reflejo** del contorno respecto de un eje vertical u horizontal por su centro.
  - **Rectángulo** por dos esquinas opuestas, como primitiva de dibujo.
  Quoted: «las herramientas basicas completas de CAD como trim exten … y demas necesito que uses
  REA para revisar esas funcionalidades en los CAD que tenemos aca instalados».
- **S5 Trim y extend no aplican todavía, y se dice.** Un `trim` recorta una entidad contra otra;
  SectionLab tiene un solo contorno cerrado, así que no hay contra qué recortar. Entra cuando el
  modelo soporte arcos y varias entidades. Se documenta en el README en vez de ofrecer un botón
  que no hace lo que promete.

- **S6 El enganche se marca como en un CAD.** La familia que el cursor atrapa se dibuja en el
  punto exacto con un glifo grueso verde sobre un halo oscuro (cuadrado extremo, triángulo punto
  medio, círculo centro, cruz intersección, `L` pie perpendicular) y su nombre en una etiqueta
  al lado, legible sobre la geometría y sobre la rejilla. Se marca también cuando la sección es
  una plantilla y solo se está midiendo: enganchar no es un privilegio de la geometría libre.
  Quoted: «el osnad no se aprecia como debe no se marca como corresponde debe verde como en un
  cad no sabes como es un CAD?»

## Tasks

| ID | Tarea | Specs | Ruta | Commit |
| --- | --- | --- | --- | --- |
| T14 | `core/edit.py`: chaflán, offset, reflejo, rectángulo | S4 | core, test-first | `72545c7` |
| T15 | Comando de dibujo explícito y Esc que conserva | S1, S2 | ui, test-first | `7dba1f3` |
| T16 | Selección múltiple, por ventana y `Supr` | S3 | ui, test-first | `7dba1f3` |
| T17 | Cinta y menús de las herramientas de edición | S4 | ui, test-first | `7dba1f3` |
| T18 | README y ayuda: qué hay y qué no (trim/extend) | S5 | docs | `7dba1f3` |
| T19 | Marcador de enganche verde y visible, también en plantillas | S6 | ui, test-first | `1429046` |

## Slices

| # | Commit | Qué entrega |
| --- | --- | --- |
| 1 | pending | geometría de edición en `core/edit.py` (T14) |
| 2 | `7dba1f3` | comando de dibujo, Esc que conserva, selección por ventana y `Supr` (T15, T16), más las herramientas de contorno y su documentación (T17, T18) |

| 3 | `1429046` | marcador de enganche como CAD (T19, S6) |

Los slices 2 y 3 se entregan en un mismo commit: los cambios se entrelazan en `ui/canvas.py` y
`ui/app.py` (una herramienta necesita el estado de comando del slice 2), y separarlos por hunks
habría producido un commit intermedio que no compila.

## Log

- **L1** (user, verbatim): «que paso con la opcion de dasactivar el comando de dibujar?  por
  ejemplo para releccionar? me hace falta eso y las herramientas basicas completas de CAD como
  trim exten sleccionar el dibujo completo y demas necesito que uses REA para revisar esas
  funcionalidades en los CAD que tenemos aca instalados y ver cuales son las que mas nos
  aportarian a nuestro proyecto. quiero que el dibujo se sienta como cuando dibujas en CAD con
  su opcion de dibujar lineas curvas arcos y demas que se sienta como dibujo CAD y herramientas
  CAD»
- **L2** (user, verbatim): «registra REA para que lo puedas usar pues has todo en orden y lo que
  se pueda en paralelo si chocar unas cosa con otra para que en esta nueva actualizacion se quede
  con mas implmentaciones.»
  Alcance de esta entrega: S1–S5. Arcos, círculos, trim, extend y filete necesitan un modelo con
  arcos y van en la siguiente (0.5.0): aquí se cierra lo que no exige cambiar el modelo.
