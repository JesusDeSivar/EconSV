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
y dice qué toca. GitHub Actions corre `datos.yml` dos veces al día de lunes a sábado (10:10 y 16:10,
hora de El Salvador): si nada toca, termina en segundos; si algo toca, lo trae, reconstruye las capas,
pasa la compuerta, guarda y publica el sitio. Una serie sigue «tocando» hasta que su período llega, y
a los diez días de atraso el workflow abre un issue. Los domingos se vuelve a traer todo para captar
las revisiones del BCR, que quedan anotadas en `lago/plata/revisiones.csv`.

**Noticias.** `noticias.yml` corre todos los días a las 7:15 AM de El Salvador (13:15 UTC). GitHub
puede arrancar una corrida programada con algunos minutos de atraso.

| Workflow | Cuándo | Qué hace |
|---|---|---|
| `datos.yml` | 10:10 y 16:10 lun–sáb; domingo 6:10 (todo) | calendario → traer lo que toca → plata → oro → compuerta → guardar → sitio |
| `noticias.yml` | 7:15 todos los días | feeds → categorías → edición del día → guardar → sitio |
| `pages.yml` | lo llaman los dos anteriores, o al cambiar el sitio | arma `sitio/datos/` y publica en GitHub Pages |
| `pruebas.yml` | en cada push y pull request | pruebas sin red, compuerta, sitio |
| `alcance.yml` | a mano | comprueba que el runner alcanza el portal del BCR y los feeds |

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
3. **Actions → Alcance → Run workflow**, para confirmar que el runner alcanza el portal del BCR.
4. **Actions → Datos del BCR → Run workflow** y **Actions → Noticias → Run workflow** para la primera publicación.

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
- El portal del BCR responde 500 a pedidos grandes; por eso el lector pide por tramos de años y por
  lotes de variables. Si el BCR cambia su portal, el lector hay que ajustarlo.

## Fuentes y licencia

Las cifras son del [Banco Central de Reserva de El Salvador](https://estadisticas.bcr.gob.sv). EconSV
no es un sitio oficial ni tiene relación con el BCR. Los titulares pertenecen a sus medios y enlazan a
ellos. El código es de licencia MIT (ver `LICENSE`).
