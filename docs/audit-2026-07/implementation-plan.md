# Audit 2026-07 — Architektur, Implementierung, UX, Security

Konsolidierter Befund und Implementierungsplan aus einem Multi-Perspektiven-Audit
(Backend/Architektur, Frontend/UX, Security/Ops, STRIDE).

## Methodik & Scope
Vier parallele Analysen des Projekts, jeweils gegen den Code auf Disk. Befunde
wurden dedupliziert, im Code stichprobenartig verifiziert und nach
Wert × Risiko × Abhängigkeit priorisiert.

**Wichtige Einordnung:** Geprüft wurde teils der WIP-Branch
`chore/security-hardening-and-deps` (Frontend), teils `main` (Backend/Ops/CI).
Frontend-Dateien unterscheiden sich zwischen beiden — die fingierte
Fortschritts-„Fassade" existiert **nur im WIP-Branch, nicht auf `main`**. Der
Plan bezieht sich auf `main` als Zielzweig.

**Bereits erledigt (nicht Teil des Plans):** Dependabot-Konsolidierung,
Auto-Merge-Fix + Grouping, pytest-CI als Required Check, release-please.
Offener Test-Backlog: #63.

## Kernbild
Die Web-/API-Schicht ist handwerklich solide (RESTful-Resources,
Marshmallow-Validierung, Backoff-Mechanik, Log-Sanitizing). Durchgehendes
Muster über alle Dimensionen: **polierte Oberfläche über nicht belastbarem
Kern** — die einzige echte Zugriffskontrolle ist unbenutzbar, das CLI ist
kaputt, und die zentrale Operation (Minuten-langes Multi-Device-Update) sprengt
das eigene Betriebsmodell.

## Was gut ist
- SSRF/IDOR mitigiert: Endpoints verarbeiten nur in `devices.yaml` konfigurierte
  IPs (Config-Match erzwungen); `is_valid_ip_address` blockt
  loopback/link-local/metadata (169.254.169.254).
- Constant-time API-Key-Vergleich, `yaml.safe_load`, Passwort-Maskierung,
  `sanitize_log_data`, keine ReDoS-Regexes.
- Non-root-Container + tini, Multi-Stage ohne gebackene Secrets.
- CORS same-origin-Default; `SECRET_KEY` zufällig bei unset.
- Frontend nutzt Alpine `x-text` (Auto-Escaping), kein `x-html`, keine Tokens im
  `localStorage`.

## Phasen (→ GitHub-Issues)

### Phase 0 — Quick Wins · #68
Risikoarme Korrektheits-/UX-/Härtungs-Fixes. **In Umsetzung / dieser PR.**
404→404, Timeout-Handler-Crash (const-Scope), Mobile-Navbar, Doppel-Fehler,
`:disabled`-Links, `[x-cloak]`, `window.open`-noopener, Security-Header +
`MAX_CONTENT_LENGTH`, `hmac`-Bytes-Vergleich, Healthcheck ohne `curl`, schwacher
`SECRET_KEY`-Default, Marshmallow-`Meta`-No-op, Container-Härtung.

### Phase 1 — Zugriffskontrolle & CSRF · #69  🔴 höchster Sicherheitswert
Auth fail-closed + UI sendet Key + `request.is_json`-Pflicht (CSRF) +
Swagger/`/version` schützen + Audit-Logging. **Design/Brainstorm vorab.**

### Phase 2 — Robustheit / DoS · #70
Rate-Limiting (schnell) + async Batch (Job-Queue, `202`+Status-Endpoint) +
`gunicorn.conf.py` im Container tatsächlich laden. **Design vorab.**

### Phase 3 — Ehrliche UX & a11y · #71  (hängt an Phase 2)
Echter Server-Fortschritt statt Fassade; Modal-a11y; Live-Batch-Balken;
Concurrency-Limit; Bestätigungsdialog mit Geräteliste.

### Phase 4 — CLI reparieren oder deprecaten · #72  ✅ erledigt (PR #82)
`tasmota_updater.py` war durch Signatur-Mismatch + Doppel-Definitionen
funktionsunfähig. **Entscheidung: deprecaten** — die ~900 Zeilen duplizierten
die Update-Logik aus `app/tasmota` und waren davon weggelaufen. Heute ist die
Datei ein Stub (Notice auf stderr, Exit 1).

**Dünne CLI-Schicht für Automatisierungen — ✅ erledigt.** Der
Deprecation-Grund war die *Duplikation*, nicht der Nutzen: ein CLI ist für
Cron/Skripte weiterhin sinnvoll (Wunsch des Users, 2026-07-26). Umgesetzt als
dünner Wrapper **über** dem gepflegten Kern in `app/tasmota`, ohne zweite
Kopie der Logik — Design und Plan:
[`2026-07-28-cli-design.md`](2026-07-28-cli-design.md),
[`2026-07-28-cli-plan.md`](2026-07-28-cli-plan.md).

Abweichungen vom ursprünglichen Backlog-Eintrag oben:

- **Verben statt Flags:** `python -m app.cli {check|update|list}` statt
  `--check-only`/`--update-all`. Drei Verben sind klarer, und die alte Syntax
  war ohnehin nicht kompatibel.
- **Kein `--dry-run`:** doppelt zum Verb `check`.
- **Kein `--non-interactive`:** die CLI ist immer nicht-interaktiv; kein
  Wizard, keine Bestätigungsabfrage vor `update`.
- **Kein Einzelgeräte-Verb** (`update <ip>`): kein Bedarf, die Web-UI deckt
  Ad-hoc-Eingriffe ab.
- **Aufruf bleibt `python -m app.cli`,** kein Konsolen-Skript: das Projekt
  wird nirgends installiert (weder lokal noch im Containerfile), ein
  Entry-Point ohne Installation existiert nicht. (`pyproject.toml` bekommt
  trotzdem einen `[project.scripts]`-Eintrag für den Fall einer Installation —
  die Doku verspricht ihn aber nicht als Standardweg.)
- `-f/--file` und `--log-level` blieben erhalten.

`docs/cli-usage.md` und die README-Feature-Liste sind wieder in Einklang mit
dem Ist-Zustand.

### Phase 5 — Architektur & Wartbarkeit · #73  (teilweise erledigt)
`updater.py` entflechten; Cache-Locking über Worker; Excepts differenzieren;
Summary-Zählung.

Zwei Punkte dieser Phase wurden vorgezogen, weil sie als Bugs im Betrieb
auffielen (v0.5.2, PR #88 / Issue #87):

- ✅ **Verifikations-Korrektheit (200 ≠ Erfolg)** — Tasmota quittiert `Upgrade 1`
  sofort mit 200 und flasht im Hintergrund weiter auf der alten Firmware.
  `verify_firmware_version_changed()` wartet jetzt auf die tatsächliche
  Versionsänderung, statt Erreichbarkeit als Erfolg zu werten.
- ✅ **Credentials via Basic-Auth statt URL** — `build_device_auth()` übergibt sie
  am `auth`-Parameter; das Passwort steckt in keiner URL mehr (und ein `:`/`@`
  im Passwort zerlegt sie nicht länger).

### Querschnitt — Threat-Model & Doku · #74
`docs/threat-models/`; README (LAN-only, Klartext-HTTP-Restrisiko);
Betreiber-Fragen (Reverse-Proxy? Internet-exponiert?) klären.

### Querschnitt — Test-Strategie & Playwright-E2E · #76
Vollständige Test-Pyramide als Ziel: **Unit** (updater/utils/Schemas) +
**Integration** (Flask-Test-Client gegen `/api/*`) + **E2E** (Playwright, headless
Chromium, gegen die App mit Fake-Devices). Harness ist gebootstrappt
(`tests/e2e/`, eigener E2E-CI-Job, Selenium ersetzt). Regel: **jede Feature-Phase
liefert ihre Testebene mit** (Phase 1 → Auth-Integration + Auth-E2E; Phase 3 →
Update-Flow-E2E). E2E-Job wird Required Check, sobald stabil.

## Feature-Backlog (außerhalb des Audits)

Wünsche, die nicht aus dem Audit stammen, aber hier mitgeführt werden, damit die
Reihenfolge im Blick bleibt. Beide setzen den fail-closed-Zugriffsschutz aus
Phase 1 voraus.

### Version und Changelog im Footer · #98
Footer zeigt die laufende Version (`app/version.py`, schon unter `/version`
verfügbar) und macht den Changelog erreichbar. Zu entscheiden: Link auf das
GitHub-Release (trivial, aber nutzlos ohne Internet — die App ist LAN-only
gedacht) oder `CHANGELOG.md` mit ins Image und lokal rendern. Ein optionaler
„neuere App-Version verfügbar"-Hinweis hätte dieselben Rate-Limit-Fallstricke wie
der Firmware-Release-Lookup, inklusive der Regel aus #91: ein fehlgeschlagener
Lookup darf nicht als „aktuell" durchgehen.

### Devices-Editor im Browser + Netzwerk-Discovery · #99
Geräteliste in der UI pflegen statt `devices.yaml` per SSH zu editieren, und
Tasmota-Geräte im LAN automatisch finden. Der Editor ist die Voraussetzung —
Discovery ohne Übernahmemöglichkeit bringt wenig —, umsetzbar aber in zwei
Schritten. Die Knackpunkte stehen im Issue; die wichtigsten:

- Schreibpfad auf die Konfiguration (atomar + Backup; das Volume muss schreibbar
  sein → Deployment-Änderung), YAML-Round-Trip verliert Kommentare.
- Geräte-Passwörter dürfen über die API nur schreibbar sein, nie zurückgelesen
  werden — sonst hebelt der Editor die Sanitize-Linie aus.
- Discovery bevorzugt per mDNS/zeroconf (braucht `network_mode: host`),
  IP-Range-Scan nur als opt-in mit begrenzter Parallelität; als Job-Modell wie
  die Batch-Updates, nicht als blockierender Request.
- Beides erweitert die Angriffsfläche spürbar → gehört vor der Umsetzung ins
  Threat-Model (#74).

## Empfohlene Reihenfolge
Phase 0 → Phase 1 → (Threat-Model-Stub) → Phase 2 → Phase 3 → Phase 4 → Phase 5.

## Blockierende Vorab-Fragen
1. Exposition: strikt LAN-only oder Internet-erreichbar? (Severity Phase 1/2)
2. Reverse-Proxy davor (TLS/CSP/Rate-Limit)?
3. CLI: reparieren oder deprecaten?
