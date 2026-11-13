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

## Where the BCR can be read from

**GitHub-hosted runners get HTTP 403 from `estadisticas.bcr.gob.sv`** — the calendar API and every
series page (two `alcance.yml` runs, 2026-11-12). Claude Code cloud sessions get 200. So the BCR chain
cannot run on `ubuntu-latest`: `datos.yml` only schedules itself when the repo variable `RUNNER_DATOS`
names a self-hosted runner, and otherwise the chain (`python tuberias/actualizar.py`) is run from a
machine that reaches the portal and pushed. Do not route around the block with proxies or disguised
headers. News feeds answer GitHub's runners normally. Run `alcance.yml` before assuming this changed.

## The scheduled BCR update (a Claude Code cloud task)

Because GitHub's runners are blocked, the owner chose on 2026-11-12 to fetch the BCR from a scheduled
Claude Code cloud task: every day at 16:10 El Salvador time a fresh session runs the chain. He
explicitly authorised that task to push **data commits under `lago/`** to `main` — that and nothing
else. If you are that session:

1. Start from the tip of `main`: `git fetch origin main && git checkout -B datos-bcr origin/main`.
2. Check write access once, before the work: `git push --dry-run origin HEAD:main` changes nothing and
   says whether this session may push. Quote its answer in the summary. On 2026-11-13 the task's
   sessions started with no repository attached (they clone because the repo is public), so a refusal
   here means the owner still has to give the task access to the repository.
3. `python -m pip install -r requirements.txt` (not bare `pip`: in that environment `pip` installs for
   another Python than `python`), then `python tuberias/actualizar.py` (on Sundays
   `python tuberias/actualizar.py --todo`, which refetches all 18 series to catch revisions).
4. Read its exit code. **0**: everything due arrived and the gate passed. **2**: the gate passed but
   the calendar or a series did not answer — keep what did arrive and say which did not. **Anything
   else**: the gate failed — commit nothing, and report the failing check.
5. If the gate passed and `git status --short lago` shows changes: `git add lago`,
   `git commit -m "Datos del BCR: <series that changed>"`, `git pull --rebase origin main`,
   `git push origin HEAD:main`. If nothing changed, push nothing. GitHub publishes the site when
   `lago/` changes on `main`.
6. In that run never edit code, catalogue, tests or workflows; never use `--aceptar-menos`; never
   work around a block or a 403. If the reader needs a fix because the BCR changed its portal, stop and
   say what broke and where — the owner decides.
7. End with a short summary in Spanish: what the dry-run answered, what was due, what arrived (series and period), how many
   revisions were logged in `lago/plata/revisiones.csv`, and what is still pending.

## What reads the gold layer from outside

`lago/oro/indicadores.csv` and `lago/oro/indicadores_catalogo.csv` are read straight from `main` by
the Apps Script in `integraciones/google_sheets/` (through raw.githubusercontent.com), and people keep
that script pasted in their own spreadsheets. So the column names of those two files, of
`lago/plata/calendario.csv` and of `lago/oro/noticias/<day>.csv` are a contract: add columns at the
end if you must, never rename or reorder them without changing `EconSV.gs` and saying so.
`node pruebas/prueba_sheets.js` runs that script against the lake in the repo with a strict stand-in
for the sheet. Text that comes from outside (headlines, names) must land in columns set to plain text
before writing, so nothing fetched can run as a formula.

## What counts as a fiscal news note

The owner writes a daily report from the news base, and its «Fiscales» section is the taste the search
follows. Which Salvadoran note is «Fiscales» is the rule `fiscales` in `catalogo/noticias_fuentes.toml`
(something fiscal, or a public-investment project, or a public actor next to money, or an international
agreement being approved), decided by the note's words and never by the section it came from. One word
alone lets in road closures and rescued dogs; too strict a rule throws out what he does include — his
11 November report carried the visa-exemption agreement with Kuwait under Fiscales. The headlines of his
reports are pinned in `pruebas/test_noticias.py` (`Fiscales`): change the lists against those tests, and
look at what `noticias.al_dia` would drop from the stored base before committing. Rule and score are
re-applied to the whole base on every run, so a change reaches the editions already stored.

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

**Pages must publish from «GitHub Actions», not «Deploy from a branch».** On 2026-11-13 the setting was
on the branch: every push to `main` (the news bot's included) started GitHub's own «pages build and
deployment» next to `pages.yml`, it finished last, and the public site showed the README rendered by
Jekyll instead of the dashboard. If the site shows the README, that is the cause: the owner changes
Settings → Pages → Source, and until then running `pages.yml` by hand (Actions → Sitio) puts the
dashboard back until the next push. After any push to `main`, look at the live site, not only at the run.

## Git

Develop on a branch and open a pull request only when asked. The news workflow commits to `main` as
`github-actions[bot]` every morning and the scheduled BCR task pushes there in the afternoon, so
`git pull --rebase` before pushing to `main`.
