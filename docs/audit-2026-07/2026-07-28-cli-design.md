# Design: dünne CLI-Schicht über `app/tasmota`

Stand 2026-07-28. Umsetzung des Backlog-Eintrags unter Phase 4 in
[`implementation-plan.md`](implementation-plan.md).

## Ziel und Abgrenzung

Eine CLI für Automatisierung (cron, Skripte), die **keine** Update-Logik
enthält, sondern den gepflegten Kern in `app/tasmota` aufruft. Der
Deprecation-Grund der alten CLI war die Duplikation von ~900 Zeilen
Update-Logik, nicht der Nutzen einer CLI. Diese Schicht darf deshalb keinen
zweiten Ausführungspfad einführen.

Nicht Ziel: Einzelgeräte-Bedienung per IP, interaktive Konfiguration,
Parallelität, ein Ersatz für die Web-UI.

## Einsatzzwecke

1. **Nächtlicher Check ohne Update** — melden, wenn Geräte veraltet sind.
2. **Unbeaufsichtigtes Update** — alles Veraltete aktualisieren, Bilanz ausgeben.
3. **Inventar** — Datenquelle für Monitoring/Skripte.

## Aufruf

Primär als Modul, ohne jede Installation:

```bash
python -m app.cli check
python -m app.cli update --timeout 300
python -m app.cli list --json
```

Im Container ohne neue Build-Schicht:

```bash
podman run --rm -v ./devices.yaml:/app/devices.yaml:ro \
  --entrypoint python dodjango/tasmota-updater -m app.cli check
```

`app/__init__.py` enthält nur `__version__` und importiert kein Flask, der
Modulaufruf zieht also keinen Server-Ballast nach.

Zusätzlich wird ein `[project.scripts]`-Eintrag
(`tasmota-updater = "app.cli:main"`) in `pyproject.toml` angelegt. Er kostet drei
Zeilen und liefert den kurzen Befehl für jeden, der das Paket installiert — die
Doku verspricht ihn aber **nicht** als Standardweg, weil das Projekt derzeit
nirgends installiert wird (weder lokal noch im Containerfile) und ein
Entry-Point ohne Installation nicht existiert.

## Befehlsfläche

```
python -m app.cli [-f PATH] [--json] [--log-level LEVEL] {check|update|list}
python -m app.cli update [--timeout SECONDS] [--force]
```

| Option | Bedeutung |
|---|---|
| `-f`, `--file PATH` | Gerätedatei. Auflösung wie im Server: `-f` schlägt `DEVICES_FILE` aus Umgebung/`.env`, sonst `devices.yaml`. |
| `--json` | Ergebnis als JSON auf stdout statt Tabelle. |
| `--log-level LEVEL` | Default `WARNING`, damit eine cron-Mail bei Erfolg schlank bleibt. |
| `--timeout SECONDS` | nur `update`: überschreibt den Gesamt-Timeout pro Gerät. |
| `--force` | nur `update`: flasht **alle** konfigurierten Geräte, auch aktuelle. |

Ohne `--force` fasst `update` nur veraltete Geräte an — die sichere
Voreinstellung für einen unbeaufsichtigten Lauf.

## Delegation an den Kern

| Verb | Aufruf |
|---|---|
| `check` | `jobs.create_batch_job(devices, check_only=True, update_only_needed=False, global_timeout=None, background=False)` |
| `update` | `jobs.create_batch_job(devices, check_only=False, update_only_needed=not force, global_timeout=timeout, background=False)` |
| `list` | `updater.get_device_firmware_version(device)` je Gerät, **ohne** `fetch_latest_tasmota_release()` |

Geräte kommen aus `utils.load_devices_from_file()`.

Den Batch-Runner zu verwenden statt selbst zu schleifen ist der Kern des
Entwurfs: er *ist* die sequenzielle Abarbeitung inklusive `update_only_needed`
und Ergebniszählung, und `background=False` existiert bereits für die Tests.
Sequenziell bleibt es bewusst — bei OTA hängt jedes Gerät minutenlang im
Flash-Fenster, und mehrere gleichzeitig rebootende Geräte im selben WLAN sind
eine unnötige Störquelle.

Zwei Eigenheiten des Runners, die die CLI berücksichtigen muss:

- `create_batch_job()` liefert `None`, wenn bereits ein Job läuft. Im frischen
  CLI-Prozess unmöglich, wird aber als interner Fehler mit Exit 2 behandelt
  statt ignoriert.
- Bei `update_only_needed=True` ruft der Runner zum Filtern für jedes Gerät
  zusätzlich `check_only=True` auf. Ein Update-Lauf prüft betroffene Geräte
  also zweimal. Akzeptiert: es ist ein HTTP-Aufruf ins LAN, und der Filter ist
  getesteter Bestandteil des Runners.

`list` benutzt den Runner nicht, weil es den Release-Lookup gerade *nicht*
braucht — es ist der einzige Pfad ohne GitHub-Abhängigkeit und damit ohne
Rate-Limit-Risiko.

## Ausgabe

stdout trägt ausschließlich das Ergebnis, stderr Logs und Fehler. Damit bleibt
`--json` unter allen Log-Leveln parsebar.

Menschenlesbar (Default), eine Zeile pro Gerät plus Bilanz:

```
192.168.8.191  tasmota-flur    14.6.0 → 15.0.1   Update verfügbar
192.168.8.192  tasmota-kueche  15.0.1            aktuell
192.168.8.193  tasmota-bad     15.0.1            Vergleich unbekannt
192.168.8.194  tasmota-keller  —                 nicht erreichbar
1 aktuell, 1 Update verfügbar, 1 Vergleich unbekannt, 1 Fehler
```

Mit `--json` ein Objekt, das die Ergebnis-Dicts des Kerns unverändert
durchreicht — `json.dumps(..., sort_keys=True)`, die Schlüssel sind also
alphabetisch sortiert, und jedes Ergebnis trägt alle Felder, die der Kern
liefert (nicht nur die für den Vergleich relevanten). Echter, unveränderter
Lauf gegen zwei Geräte (eines per Fake-Firmware, eines mit ungültiger IP, um
einen echten Fehlerfall zu zeigen):

```json
{
  "command": "check",
  "devices_file": "devices-doc-example.yaml",
  "exit_code": 2,
  "results": [
    {
      "current_version": "12.0.2",
      "dns_name": "fake-tasmota-light1.local",
      "ip": "192.168.100.101",
      "latest_version": "15.5.0",
      "message": "Update available",
      "needs_update": true,
      "success": true,
      "timeout_config": {
        "initial_wait": 10,
        "max_check_interval": 30.0,
        "min_check_interval": 2.0,
        "total_timeout": 240
      },
      "timeout_report": null,
      "update_completed": false,
      "update_started": false,
      "version_verification": null
    },
    {
      "current_version": "Unknown",
      "dns_name": "localhost",
      "ip": "127.0.0.1",
      "latest_version": "Unknown",
      "message": "Failed to get current firmware version",
      "needs_update": false,
      "success": false,
      "timeout_config": {
        "initial_wait": 10,
        "max_check_interval": 30.0,
        "min_check_interval": 2.0,
        "total_timeout": 240
      },
      "timeout_report": null,
      "update_completed": false,
      "update_started": false,
      "version_verification": null
    }
  ],
  "summary": {
    "comparison_unknown": 0,
    "failed": 1,
    "needs_update": 1,
    "total": 2,
    "up_to_date": 0
  }
}
```

Der `exit_code` ist hier **2** und nicht 1, weil ein Fehler das „veraltet"
überstimmt — genau die Präzedenz, die unten im Abschnitt Exit-Codes
beschrieben ist. `comparison_unknown` steht in diesem Lauf auf 0, weil der
Release-Lookup erfolgreich war; die Zuordnung, wann dieses Feld greift, steht
in der Tabelle unten.

Bei `list` fehlen in den Ergebnissen die Vergleichsfelder (`latest_version`,
`needs_update`) und in der Bilanz entsprechend `up_to_date`, `needs_update` und
`comparison_unknown` — dort gibt es nur `total` und `failed`, weil kein
Release-Lookup stattfindet.

Die CLI berechnet `summary` **selbst** aus `results`. Die Summary des
Job-Runners (`total`, `processed`, `success`, `needs_update`, `updated`) kann
den Zustand „Vergleich unbekannt" nicht ausdrücken, und `success` unterscheidet
nicht zwischen „aktuell" und „nicht vergleichbar". Die Zuordnung:

| Bilanz-Feld | Bedingung im Ergebnis-Dict |
|---|---|
| `failed` | `success` falsch |
| `comparison_unknown` | `success` wahr, aber `latest_version` fehlt oder ist `"Unknown"` |
| `needs_update` | `needs_update` wahr |
| `up_to_date` | `success` wahr, `latest_version` bekannt, `needs_update` falsch |

## Exit-Codes

| | `check` | `update` | `list` |
|---|---|---|---|
| **0** | alles aktuell | nichts zu tun oder alle Updates erfolgreich | alle Geräte erreichbar |
| **1** | mindestens eines veraltet | — | — |
| **2** | Fehler | ein Flash fehlgeschlagen, oder ein Gerät war unerreichbar/nicht vergleichbar — auch eines, das `update` gar nicht angefasst hat | mindestens eines unerreichbar |

Bei gemischten Ergebnissen gewinnt der höhere Code: Fehler (2) schlägt
veraltet (1) schlägt in Ordnung (0). Exit 1 tritt nur bei `check` auf.

Bei `update` heißt Exit 2 also nicht zwingend, dass ein Flash-Versuch
scheiterte: `update` klassifiziert zuerst alle Geräte und flasht nur die
ausgewählten (veraltete, oder mit `--force` alle erreichbaren/vergleichbaren).
Ein nicht erreichbares oder nicht vergleichbares Gerät wird nie geflasht, zählt
aber trotzdem in `failed`/`comparison_unknown` und hebt den Exit-Code
weiterhin auf 2 — derselbe Effekt wie bei `check`, nur leichter
missverständlich, weil man bei `update` zuerst an einen fehlgeschlagenen
Flash denkt.

Damit reicht für cron ein Einzeiler, ohne `jq`:

```bash
python -m app.cli check || mail -s "Tasmota veraltet" me@example.com
```

**Die wichtigste Regel des Entwurfs:** `needs_update: false` bedeutet auch
„konnte nicht vergleichen" (gescheiterter Release-Lookup →
`latest_version: "Unknown"`). Das darf **nie** als „alles aktuell, Exit 0"
erscheinen — es wäre der Zwilling des UI-Bugs aus #91, nur folgenschwerer, weil
ein cron-Job dann dauerhaft schweigt. Ein unbekannter Vergleich ist ein Fehler
(Exit 2) und heißt in der Ausgabe `Vergleich unbekannt`.

## Fehlerbehandlung

| Fall | Verhalten |
|---|---|
| Gerätedatei fehlt oder ist ungültiges YAML | Meldung auf stderr, Exit 2, kein Gerät angefasst |
| Leere Geräteliste | Meldung auf stderr, Exit 2 (eine leere Konfiguration ist kein Erfolg) |
| Gerät unerreichbar | Zeile im Ergebnis, Lauf geht weiter, am Ende Exit 2 |
| Release-Lookup gescheitert | `Vergleich unbekannt`, Exit 2 |
| `create_batch_job()` liefert `None` | Meldung auf stderr, Exit 2 |
| `Ctrl-C` während eines Updates | `KeyboardInterrupt` wird gefangen, Warnung auf stderr, Exit 2 — mit dem ausdrücklichen Hinweis, dass ein laufender OTA-Flash auf dem Gerät weiterläuft und nicht abgebrochen wurde |

## Tests

Unit-Tests über den Wrapper mit gemocktem Kern:

- Argument-Parsing je Verb, inklusive der Ablehnung von `--timeout`/`--force`
  bei `check` und `list`.
- Die vollständige Exit-Code-Matrix, ausdrücklich mit dem Unknown-Fall und der
  Präzedenz bei gemischten Ergebnissen.
- Bilanz-Zuordnung aus `results` (die vier Felder oben).
- Bei `--json` liegt auf stdout ausschließlich JSON, auch mit
  `--log-level DEBUG`.

Dazu ein Smoke-Test im Subprozess gegen `devices-dev.yaml` (Fake-Geräte), wie
es die e2e-Suite mit dem Server macht: `list --json` und `check --json`. Beim
`check` wird der Release-Lookup gestubbt — der Live-Aufruf macht CI flaky, das
ist die Lehre aus #76. Keine neuen pytest-Marker; die Tests laufen im grünen
Kern.

## Doku-Abgleich

Gehört in denselben PR, sonst driftet es wie zuvor:

- `docs/cli-usage.md` neu schreiben: Deprecation-Banner raus, die alten
  Optionen (`--update-all`, `--example`, Wizard) ausdrücklich als entfallen
  benennen.
- `README.md`: „Two supported interfaces" → drei; der Absatz, der die CLI für
  tot erklärt, muss weg.
- `CLAUDE.md`: „There is **no working CLI**" korrigieren.
- `tasmota_updater.py`: bleibt Stub, verweist künftig auf `python -m app.cli`.
- `implementation-plan.md`: Backlog-Eintrag als erledigt markieren, mit den
  Abweichungen.

PR-Titel `feat(cli): …` — das ergibt bewusst einen Minor-Bump.

## Entscheidungen und Verworfenes

| Verworfen | Grund |
|---|---|
| `--dry-run` | Doppelt zum Verb `check`. |
| `--non-interactive`, Konfigurations-Wizard | Die CLI ist immer nicht-interaktiv; ein `update` fasst Geräte an, das ist der Zweck des Aufrufs. |
| Bestätigungsabfrage vor `update` | Ebenso — würde den cron-Einsatz gerade verhindern. |
| Einzelgeräte-Verb (`update <ip>`) | Kein Bedarf; die Web-UI deckt Ad-hoc-Eingriffe ab. |
| Begrenzte Parallelität | Wenige Geräte, und rebootende Geräte im selben WLAN sind eine Störquelle. |
| `tasmota_updater.py` wiederbeleben | Die alte, kaputte CLI soll nicht zurückkehren; der Stub bleibt Wegweiser. |
| Installation (`pip install .`) zur Voraussetzung machen | Würde Container-Build und Setup-Anleitung für ein Feature ändern, das sonst nichts davon braucht. |
| Flags statt Verben (`--check-only`, `--update-all`) | Drei Verben sind klarer; die alte Syntax ist ohnehin nicht kompatibel. |

`list` bleibt trotz Überlappung mit `check --json` erhalten: es braucht keinen
GitHub-Aufruf und liefert nie Exit 1.

## Restrisiken

- Dass `update` gegen echte Hardware trägt, zeigt erst ein Lauf am Gerät —
  Fake-Geräte reproduzieren das OTA-Flash-Fenster nicht (dieselbe Einschränkung
  wie bei #87).
- Der Timeout-Default kommt aus der Gerätekonfiguration. Ein zu knapper Wert
  äußert sich als Fehlschlag, obwohl der Flash im Hintergrund noch läuft; das
  ist Verhalten des Kerns, nicht der CLI.
