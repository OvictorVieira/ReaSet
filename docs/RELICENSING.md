# Relicenciamiento a v3.0 — cómo se estableció que era posible

ReaSet pasó de **GPL v3** a una **licencia propietaria con permiso de uso
gratuito** en la v3.0 (2026-08-11). Este documento registra la evidencia, para
que la pregunta "¿se podía?" no haya que reconstruirla más adelante.

Relicenciar solo es posible si quien lo hace es titular de todo el código que
cubre la nueva licencia. Había tres cosas que verificar.

---

## 1. La cabecera de `Reaset.lua` declaraba una herencia GPL — y era falsa

La cabecera decía:

```
Credits:
  - Lyrics/Chords note bridge logic: X-Raym (GPL v3)
Licence: GPL v3 (inherits from the X-Raym components it reuses).
```

Si esa derivación existiera, el copyleft sería real y no habría nada que
discutir. **Se midió, y no existe.**

Comparación línea a línea de `Reaset.lua` contra
`Legacy/X-Raym_Convert Lyrics track items notes...lua`, ignorando comentarios y
líneas en blanco:

| | |
|---|---|
| Líneas de código en el script de X-Raym | 119 |
| Líneas de código en `Reaset.lua` | 354 |
| **Líneas idénticas compartidas** | **18** (15,1 % del script de X-Raym) |
| Bloques compartidos de 2+ líneas con contenido real | **ninguno** |
| Funciones de X-Raym presentes en `Reaset.lua` | **ninguna** de las 8 |

Las 18 líneas son, textualmente: `end`, `end`, `end`, `break`, `end` y
repeticiones de lo mismo. Son ruido sintáctico de Lua, no expresión creativa —
cualquier par de scripts del mismo lenguaje los comparte.

**Conclusión:** `Reaset.lua` resuelve el mismo problema que los scripts de
X-Raym, con su propia implementación. La cabecera declaraba una obligación de
copyleft que el código nunca contrajo. Se corrigió: ahora acredita la
inspiración sin afirmar derivación.

Esta medición ya constaba en el repo Pro (`PRO_FEATURES.md` §5) y se rehízo de
forma independiente antes del cambio.

---

## 2. Los scripts de X-Raym siguen siendo de X-Raym

Los archivos de `Legacy/` **sí** son obra de terceros bajo GPL v3, y **no se
relicenciaron**. Se conservan con su autoría y su licencia declaradas en
`Legacy/LICENSE-NOTICE.md`, fuera del alcance del `LICENSE` de ReaSet.

Están superados por `Reaset.lua` y se mantienen por atribución y trazabilidad.

---

## 3. ReaSetlistManager de suckyble: inspiración, no código

ReaSet nació inspirado en
[ReaSetlistManager](https://github.com/suckyble/ReaSetlistManager). El README lo
acredita desde el principio, en ambos idiomas.

**No se copió código.** Lo que se tomó fueron ideas de producto —la noción de
manejar un setlist sobre las regiones de REAPER desde una interfaz web—, y las
ideas no son objeto de derecho de autor. No hay archivos, funciones ni bloques
provenientes de ese proyecto.

Además se pidió y se obtuvo el visto bueno del autor. Esa autorización
**consta por correo electrónico** y el titular conserva el mensaje; es la prueba
documental de este punto.

---

## 4. Qué NO cambia

**Las versiones publicadas bajo GPL v3 siguen bajo GPL v3, para siempre.**
Quien obtuvo una copia hasta la v2.x conserva todos sus derechos sobre esa
versión: puede usarla, estudiarla, modificarla, redistribuirla y forkearla bajo
GPLv3, sin límite de tiempo.

El relicenciamiento **no es retroactivo y no pretende serlo**. Aplica a la v3.0
en adelante.

---

## 5. Por qué no MIT

Se consideró MIT y se descartó a propósito. MIT permitiría a cualquiera —
incluido un competidor directo — tomar ReaSet, cerrarlo y venderlo.

La licencia elegida conserva la propiedad que se buscaba (poder incluir este
código en un producto comercial cerrado) sin conceder ese mismo derecho a
terceros, y manteniendo el uso gratuito e irrestricto para los músicos, que es
a quienes está dirigido.

---

## 6. Recomendación

La mecánica de arriba es sólida y está documentada. Los puntos 1 y 2 descansan
en una medición reproducible; el punto 3 descansa en un correo, que hay que
**conservar archivado** —con cabeceras completas— junto al resto de la
documentación legal del proyecto.

Antes de un lanzamiento comercial conviene igualmente que un abogado revise el
conjunto. El correo prueba el permiso, pero no sustituye a una revisión de sus
términos exactos (si es revocable, si cubre uso comercial) ni al criterio
profesional sobre el resto.
