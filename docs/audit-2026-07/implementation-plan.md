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

### Phase 4 — CLI reparieren oder deprecaten · #72
`tasmota_updater.py` ist durch Signatur-Mismatch + Doppel-Definitionen
funktionsunfähig. Entscheidung: Kernfunktionen wiederverwenden **oder**
deprecaten.

### Phase 5 — Architektur & Wartbarkeit · #73
`updater.py` entflechten; Cache-Locking über Worker; Excepts differenzieren;
Verifikations-Korrektheit (200 ≠ Erfolg); Credentials via `HTTPBasicAuth`;
Summary-Zählung.

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

## Empfohlene Reihenfolge
Phase 0 → Phase 1 → (Threat-Model-Stub) → Phase 2 → Phase 3 → Phase 4 → Phase 5.

## Blockierende Vorab-Fragen
1. Exposition: strikt LAN-only oder Internet-erreichbar? (Severity Phase 1/2)
2. Reverse-Proxy davor (TLS/CSP/Rate-Limit)?
3. CLI: reparieren oder deprecaten?
