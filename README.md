# EconSV — signos vitales de la economía salvadoreña

Un tablero de la economía de El Salvador hecho con información pública del Banco Central de Reserva
(BCR), que se actualiza solo según el calendario de publicación de cada dato, más un resumen de
noticias cada mañana. La idea viene de [Econvitals](https://econvitals.org), que hace esto para
Estados Unidos.

**Sitio:** <https://jesusdesivar.github.io/EconSV/> (cuando GitHub Pages esté activado; ver «Puesta en marcha»).

## Qué muestra

| Sección | Indicadores |
|---|---|
| Actividad | PIB anual (real y nominal), PIB trimestral (real, nominal, desestacionalizado), IVAE e IVAE por actividad |
| Precios | Inflación al consumidor (IPC y subyacente), por división del IPC, e inflación al productor (IPP) |
| Sector externo | Remesas, exportaciones e importaciones, balanza comercial, cuenta corriente, inversión extranjera directa (total y por sector), posición de inversión internacional neta, reservas internacionales |
| Turismo | Ingresos y gastos por viajes (balanza de pagos), entrada y salida de pasajeros, valor agregado de alojamiento y comidas |
| Construcción | IVAE de la construcción, valor agregado de la construcción (real y nominal), consumo aparente de cemento |
| Calendario | Cuándo se espera cada dato y hasta dónde llega cada serie |
| Noticias | Tabla diaria en cinco categorías, descargable en CSV y Excel |
| Datos | Cada serie del BCR completa, en CSV y Excel |

Cada gráfica ofrece varias vistas (nivel, variación anual o del período, suma de 12 meses o 4
trimestres, % del PIB), su tabla y su descarga.

## Cómo se actualiza

**Datos.** El BCR publica un [calendario de divulgación](https://estadisticas.bcr.gob.sv/calendario-de-divulgacion)
con la fecha de cada cuadro. `tuberias/calendario.py` lo baja, lo compara con lo que el lago ya tiene
y dice qué toca. La actualización es siempre la misma cadena: calendario → traer lo que toca → plata →
oro → compuerta → guardar. Si nada toca, termina en segundos y no guarda nada. Una serie sigue
«tocando» hasta que su período llega, y pasa a «atrasada» a los diez días. Una vez por semana conviene
traer todo otra vez, para captar las revisiones del BCR, que quedan anotadas en `lago/plata/revisiones.csv`.

**Dónde corre esa cadena.** El portal del BCR responde 403 a los runners que GitHub presta
(comprobado el 2026-11-12 con `alcance.yml`), así que GitHub no puede traer los datos del BCR con sus
propias máquinas. Hay tres maneras, y las tres terminan igual: en cuanto `lago/` cambia en `main`,
GitHub publica el sitio.

1. **Un runner propio** (self-hosted) en una computadora que sí alcance al BCR. Se registra en
   Settings → Actions → Runners y se crea la variable `RUNNER_DATOS = self-hosted`; desde ahí
   `datos.yml` corre solo, a las 10:10 y 16:10 de lunes a sábado y el domingo a las 6:10 (todo).
2. **Una tarea programada fuera de GitHub** (por ejemplo, una sesión de Claude Code en la nube, que sí
   alcanza al BCR) que corre la cadena y hace `git push`.
3. **A mano**, cuando la página Calendario del sitio dice que algo toca:
   `python tuberias/actualizar.py` y `git push`.

**Noticias.** Los feeds sí responden a los runners de GitHub: `noticias.yml` corre todos los días a
las 7:15 AM de El Salvador (13:15 UTC). GitHub puede arrancar una corrida programada con algunos
minutos de atraso.

| Workflow | Cuándo | Qué hace |
|---|---|---|
| `noticias.yml` | 7:15 todos los días | feeds → categorías → edición del día → guardar → sitio |
| `pages.yml` | cuando cambia `lago/`, `sitio/` o `catalogo/` en `main`, y lo llaman los otros | arma `sitio/datos/` y publica en GitHub Pages |
| `datos.yml` | 10:10 y 16:10 lun–sáb, domingo 6:10; solo con un runner propio (`RUNNER_DATOS`) | la cadena de datos del BCR |
| `pruebas.yml` | en cada push y pull request | pruebas sin red, compuerta, sitio |
| `alcance.yml` | a mano | dice si el runner alcanza el portal del BCR y los feeds |

## Cómo está armado

Un lago de datos en tres capas, todo en texto y versionado: el historial de git es el archivo de
versiones.

```
catalogo/series.toml            las 18 series del BCR: dirección, frecuencia, título en el calendario
catalogo/indicadores.toml       las gráficas del sitio: qué variable, qué vistas
catalogo/noticias_fuentes.toml  los feeds, sus categorías y las palabras del reparto
lago/bronce/                    lo que sirve el BCR, sin tocar, con su sha256 (fuentes.lock.json)
lago/plata/                     lo mismo en tablas largas; calendario, noticias y bitácora de revisiones
lago/oro/                       lo que EconSV calcula: indicadores.csv y la edición diaria de noticias
tuberias/bcr.py                 el lector del portal del BCR (HTTP, sin navegador)
tuberias/traer.py               bronce: bcr | calendario | noticias | verificar
tuberias/plata.py · oro.py      construyen cada capa (--check dice si están al día)
tuberias/calendario.py          qué toca hoy
tuberias/actualizar.py          la cadena completa de los datos del BCR, en una orden
tuberias/noticias.py            feeds → categorías → ediciones
tuberias/verificar.py           la compuerta
tuberias/sitio.py               el lago → sitio/datos/
sitio/                          index.html, app.js, estilo.css (sin bibliotecas externas)
pruebas/                        pruebas sin red
```

Reglas que sostienen las cifras:

- **Una sola cuenta.** Toda cifra del sitio es del BCR o se calcula solo con cifras del BCR.
- **Lo que se trae se contrasta.** El portal entrega cada serie en dos caras (los datos de la gráfica y
  una tabla); una serie se guarda solo si las dos dicen lo mismo y si contiene lo que la página muestra
  al abrir. Una serie que llega con menos cifras que antes no reemplaza a la que está.
- **La compuerta.** Antes de publicar: cada archivo contra su sha256, plata y oro al día, las sumas
  que el propio BCR imprime (RIN = activos − pasivos, PIB = suma de actividades, saldo = X − M…) y
  ninguna serie con huecos. La tolerancia de cada suma depende de los decimales con que se publicó.
- **Las noticias son contexto.** Solo titular, extracto y enlace, como los publica cada medio en su
  feed. Nunca texto completo, y nunca son la fuente de una cifra. El reparto en categorías es por
  coincidencia de palabras y se equivoca a veces.

## Correrlo en tu máquina

Python 3.11 o más reciente.

```bash
pip install -r requirements.txt

python tuberias/actualizar.py                 # todo de una vez: trae lo que toca, reconstruye y verifica
python tuberias/actualizar.py --todo          # lo mismo con las 18 series, toquen o no

python tuberias/calendario.py                 # qué toca hoy
python tuberias/traer.py calendario           # baja el calendario del BCR
python tuberias/traer.py bcr --solo reservas  # trae una serie (sin --solo, las 18: unos 4 minutos)
python tuberias/plata.py && python tuberias/oro.py
python tuberias/noticias.py                   # el resumen de noticias
python tuberias/verificar.py                  # la compuerta
python -m unittest discover -s pruebas        # pruebas sin red

python tuberias/sitio.py                      # arma sitio/datos/
python -m http.server --directory sitio 8000  # y se ve en http://localhost:8000
python tuberias/noticias.py excel             # el Excel de la última edición
```

## Puesta en marcha (una vez)

1. Fusionar este trabajo a `main`: las corridas programadas de GitHub solo salen de la rama principal.
2. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
3. **Actions → Noticias → Run workflow** para la primera edición y la primera publicación del sitio.
4. Elegir cómo se traen los datos del BCR (las tres maneras de arriba).

## Agregar cosas

- **Una serie del BCR:** un bloque en `catalogo/series.toml` con su dirección en
  `estadisticas.bcr.gob.sv/serie/…`, y `python tuberias/traer.py bcr --solo <clave>`.
- **Una gráfica:** un bloque en `catalogo/indicadores.toml` con el `id` de la variable (está en
  `lago/plata/bcr_variables.csv`) y sus vistas.
- **Una fuente de noticias:** un bloque en `catalogo/noticias_fuentes.toml`; `python tuberias/noticias.py --seco`
  muestra cómo queda el reparto sin escribir nada.

## Límites conocidos

- El turismo y la construcción se miden con lo que publica el BCR. Las llegadas de visitantes de
  MITUR/CORSATUR no están: el sitio de MITUR respondió 403 a la lectura automática.
- La inversión extranjera en construcción es confidencial en casi todos los trimestres.
- El feed del Ministerio de Hacienda y el de la Presidencia respondieron 403 al armar el catálogo;
  están marcados como opcionales y se prueban en cada corrida.
- El portal del BCR responde 403 a los runners de GitHub: sus datos se traen desde otra máquina.
- El portal del BCR responde 500 a pedidos grandes; por eso el lector pide por tramos de años y por
  lotes de variables. Si el BCR cambia su portal, el lector hay que ajustarlo.

## Fuentes y licencia

Las cifras son del [Banco Central de Reserva de El Salvador](https://estadisticas.bcr.gob.sv). EconSV
no es un sitio oficial ni tiene relación con el BCR. Los titulares pertenecen a sus medios y enlazan a
ellos. El código es de licencia MIT (ver `LICENSE`).
