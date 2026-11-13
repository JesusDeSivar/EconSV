# EconSV en Google Sheets

Un script de Google Apps Script que trae la capa oro de EconSV a una hoja de cálculo, para trabajar
con los datos: graficar, cruzar, armar tablas dinámicas. Lee los CSV públicos de este repositorio
(rama `main`, carpeta `lago/`) y no necesita claves ni cuentas.

## Instalarlo (una vez, unos dos minutos)

1. Crea una hoja de cálculo nueva en [Google Sheets](https://sheets.new).
2. **Extensiones → Apps Script.** Borra lo que haya en `Código.gs`, pega el contenido completo de
   [`EconSV.gs`](EconSV.gs) y guarda (ícono del disquete).
3. Vuelve a la hoja y recárgala. Aparece el menú **EconSV**.
4. **EconSV → Actualizar todo.** La primera vez Google pide permiso. Como el script es tuyo y Google
   no lo ha revisado, muestra «Google no ha verificado esta aplicación»: *Configuración avanzada →
   Ir a (nombre del proyecto) → Permitir*. Pide tres cosas: ver y editar **esta** hoja (no las demás
   de tu cuenta), conectarse a un servicio externo (GitHub, para leer los CSV) y crear disparadores
   (la actualización automática).
5. Opcional: **EconSV → Programar actualización automática.** Desde ahí la hoja se pone al día sola
   todos los días entre las 8 y las 9 AM y entre las 5 y las 6 PM, hora de El Salvador.

`appsscript.json` es opcional: fija la zona horaria y deja los permisos en el mínimo. Para usarlo, en
el editor de Apps Script: *Configuración del proyecto → Mostrar el archivo de manifiesto*, y pega su
contenido.

## Qué deja en la hoja

| Hoja | Qué tiene |
|---|---|
| **Mensual**, **Trimestral**, **Anual** | Una fila por período y una columna por serie, de la más antigua a la más reciente. Las dos primeras columnas son la fecha y el período. Listas para graficar. |
| **Oro** | La tabla larga tal como está en el lago: `indicador`, `linea`, `vista`, `fecha`, `periodo`, `valor`. Para tablas dinámicas y `QUERY`. |
| **Diccionario** | Qué es cada serie: título, unidad, frecuencia, de qué variable del BCR sale, qué tramo cubre, su último valor, y en qué hoja y columna está. |
| **Calendario** | Cuándo se espera el próximo dato de cada serie. |
| **Noticias** | Las ediciones de los últimos siete días del resumen de noticias: categoría, fuente, titular, extracto, enlace y relevancia (dentro de cada categoría, primero lo que más se parece al reporte diario). |
| **EconSV** | Cuándo se actualizó y qué llegó. |

Cada serie viene en varias vistas, y cada vista es una columna: `nivel` (la cifra del BCR),
`var. anual %`, `var. mensual %` o `var. trimestral %`, `suma 12 meses` o `suma 4 trimestres`,
`% del PIB` y, para las reservas, `meses de importación`. El `% del PIB` de una serie mensual está en
la hoja **Trimestral**, porque el PIB es trimestral.

## Trabajar con los datos

**Estas hojas se reemplazan enteras en cada actualización.** Lo tuyo —gráficas, cálculos, notas— va
en otras hojas que apunten a estas; así una actualización nunca te borra nada.

- Una gráfica: selecciona la columna `Fecha` y la columna de la serie en **Mensual** e *Insertar →
  Gráfico*.
- Una serie por nombre, sin depender de en qué columna cayó:

  ```
  =QUERY(Oro!A:F; "select D, F where A = 'remesas' and C = 'suma_anual' order by D"; 0)
  ```

  (Con coma en lugar de punto y coma si tu hoja está en inglés.) Las claves de `indicador` y `vista`
  están en **Diccionario**.
- El último dato de un indicador, en todas sus vistas (encabezado, período y valor):

  ```
  =QUERY(Diccionario!A:P; "select C, N, O where D = 'remesas'"; 1)
  ```

## Cosas que conviene saber

- GitHub sirve estos archivos con unos cinco minutos de caché: un dato recién publicado puede tardar
  ese rato en verse.
- Las cifras son del Banco Central de Reserva de El Salvador; las variaciones, sumas y porcentajes del
  PIB los calcula EconSV. Las noticias son solo titular, extracto y enlace.
- Todo texto que viene de fuera (titulares, nombres) se escribe en celdas de texto, así que nada de lo
  que llega puede ejecutarse como fórmula.
- Para apuntar a otra copia del lago, cambia `ORIGEN` al principio del script.

## Probarlo sin Google

`node pruebas/prueba_sheets.js` corre el script con el lago del repositorio y un doble estricto de la
hoja. Comprueba las tablas, los encabezados, el orden, el manejo de fallas y que ningún texto externo
caiga en una celda que Sheets interprete. No prueba lo que solo Google puede: permisos y cuotas.
