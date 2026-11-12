# CLAUDE.md

Guidance for Claude Code when working in this repository. The README (Spanish) explains what the
project is and how it is laid out; this file holds what an agent needs that the README does not say.

## This repository is public

Everything committed here is visible to anyone. So:

- **Nothing from a private repository comes in here** — no code, no data files, no analysis, no
  graphic identity. The owner allowed exactly two things to be carried over from his private fiscal
  repo: the addresses of public sources, and the bronce/plata/oro idea. Do not widen that.
- **News is headline, excerpt and link only**, as each outlet publishes them in its own feed. Never
  store or republish article text. `largo_resumen` caps the excerpt; `verificar.py` enforces it.
- **No secrets, no personal data.** Requests to outside services use a generic User-Agent; do not put
  the owner's name, e-mail or the repo name in headers or URLs.

## Rules that hold for every figure

- **One account.** Every figure is the BCR's or is computed only from BCR figures. Do not add a second
  publisher into a calculation; if a second source is ever added, it gets its own files and its own
  charts, and the site says which is which.
- **Edit the scripts, never the CSVs.** `lago/bronce/` is what the publisher served; `plata` is rebuilt
  from bronce by `plata.py`, `oro` from plata by `oro.py`. `--check` on each says whether it is stale.
- **The gate must pass** (`python tuberias/verificar.py`) before anything is committed to `lago/`.
  A failing identity is information: look at the periods it names before touching the tolerance.
  Two published misprints in the reserves table are pinned in `FIJADAS`; if the BCR fixes them the
  gate will say so, and the pin is removed.
- **A series that arrives with fewer figures than before is not written.** `--aceptar-menos` exists
  for the case where the BCR really rebuilt a table; use it only after looking.
- **Variable ids are the keys.** `catalogo/indicadores.toml` names each variable by its portal id plus
  the label it must carry (`rotulo`); `oro.py` fails if the label no longer matches.

## How the BCR portal is read (`tuberias/bcr.py`)

Learned the hard way on 2026-11-12; re-check before changing the reader.

- `estadisticas.bcr.gob.sv` is a Livewire v2 app. GET the series page (cookie, CSRF token, the
  component's `wire:initial-data`), then POST to `/livewire/message/vista-serie` with the component
  state and the updates. No browser is needed.
- A series comes in one of two shapes. **`grafica`**: the server returns `graficaPredefinida` (one
  array per variable) and `fechas_unicas`; select every variable with `filtroVariables` +
  `filtrarVariablesGraficasPredefinidas`, then set the range and call `filtrar`. **`tabla`** (IPC, ISI,
  IPP): no chart data; set `vars` and the range, call `filtrar`, read the HTML table.
- In `grafica` shape **the HTML table is scrambled**: its cells run period by period, in arbitrary
  order inside each period, not row by row. It is only good as a cross-check (same multiset of figures
  per period), and to tell an empty cell (`''`) from a real zero — the chart sends 0 for both.
  Sentinels in the chart: −3000000 = ND, −6000000 = C (confidential).
- The server answers **500/502 to large responses**: ask by windows of years (4 for monthly, 10 for
  quarterly) and by batches of 30 variables. It also answers 500 to some ranges depending on what the
  same page asked before; `Consulta` retries once on a fresh page.
- Period fields: `nInicio`/`nFin` take unpadded numbers (`"1"`, not `"01"`) for quarterly series.
- The release calendar is a plain JSON API: `/api/calendario-api?lang=es&start=&end=`. The BCR
  announces one title per family of tables (see the comment in `catalogo/series.toml`).
- `www.bcr.gob.sv` (the news feed) sits behind a firewall that sometimes answers «Request Rejected»
  with HTTP 200. That source is optional.

## Schedules

GitHub cron is UTC and El Salvador is UTC−6 all year (no daylight saving): 7:15 AM = `15 13 * * *`.
Scheduled workflows only run from the default branch. A push made with `GITHUB_TOKEN` does not trigger
other workflows, which is why `datos.yml` and `noticias.yml` call `pages.yml` directly.

## The site

`sitio/` is static, with no external libraries or requests: `app.js` draws SVG itself. Colours live in
`estilo.css` as roles (light and dark); the JS writes no hex. A time chart carries one or two lines;
more categories than that is a `ranking`. Every chart has a table view and a CSV, a tooltip that also
works from the keyboard, and data strings enter the DOM with `textContent`. After changing the site,
run `python tuberias/sitio.py`, serve `sitio/` and look at it in a browser at desktop and phone width,
in both colour schemes, before calling it done. `sitio/datos/` is built, not committed.

## Git

Develop on a branch and open a pull request only when asked. The scheduled workflows commit to `main`
as `github-actions[bot]`, so `git pull --rebase` before pushing there.
