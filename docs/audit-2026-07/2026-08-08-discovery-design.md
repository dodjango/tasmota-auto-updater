# Design: Tasmota-Discovery im Netzwerk

Stand 2026-08-08. Zweiter von zwei Zyklen zu [#99](https://github.com/dodjango/tasmota-auto-updater/issues/99).
Der erste Zyklus — der Geräte-Editor — ist mit
[#128](https://github.com/dodjango/tasmota-auto-updater/pull/128) fertig und ist
die Voraussetzung: Discovery liefert Vorschläge, der Editor nimmt sie auf.

## Ziel und Abgrenzung

Tasmota-Geräte im LAN finden und mit Auswahl in die Geräteliste übernehmen,
statt IPs von Hand zusammenzusuchen.

Nicht Ziel: automatische Übernahme, dauerhafte Überwachung des Netzes,
Erkennung verschwundener Geräte, MQTT-basierte Discovery, IPv6,
Discovery über die CLI.

## Getroffene Entscheidungen

Diese fünf hat der Betreiber entschieden; sie sind die Grundlage von allem
Weiteren.

| Frage | Entscheidung |
|---|---|
| Betriebsmodell? | **Beides muss funktionieren** — Container im Bridge-Netz *und* Host-Betrieb. mDNS kann im Bridge-Netz nichts finden; das wird gesagt, nicht kaschiert. |
| Methodenwahl? | **Der Nutzer wählt explizit.** Zwei getrennte Aktionen, kein automatischer Fallback vom einen ins andere. |
| Scan-Bereich? | **UI-Eingabe mit harten Server-Grenzen.** Vorbelegt aus dem erkannten Interface-Netz, serverseitig auf privat und ≥ /22 begrenzt. |
| Übernahme? | **In den Editor, der Nutzer speichert.** Discovery bekommt keinen Schreibpfad. |
| Oberflächen? | **API und Web-UI, keine CLI.** Discovery ist interaktiv und hätte keinen sinnvollen Exit-Code-Vertrag. |

Zur dritten Zeile: das erkannte Netz ist ein *Vorschlag*, keine Feststellung.
Die Ermittlung liefert die eigene Interface-IP, nicht deren Präfixlänge; /24
ist eine Annahme. Deshalb heißt das Feld `suggested_networks` und die UI zeigt
es als editierbares Feld.

## Warum ein Job und kein synchroner Request

mDNS braucht rund vier Sekunden Sammelzeit, ein /24 mit 64 parallelen Sockets
rund acht, ein /22 rund fünfundzwanzig. Ein synchroner Request liefe damit
gegen den Gunicorn-Timeout — und weil im Betrieb genau *ein* gthread-Worker
läuft (`gunicorn.conf.py`), würde er nebenbei die ganze Anwendung blockieren.

Discovery läuft deshalb im selben Muster wie die Batch-Updates:
`POST` → `202 {job_id}` → Polling über `GET /api/jobs/<id>`.

### Der Deadlock, den das mitbringt

`jobs.py` kennt heute nur eine Job-Art. `batch_in_progress()` und die
Exklusivitätsprüfung in `create_batch_job()` schauen auf **alle** Jobs im
Store. Ein zweiter Job-Typ im selben Store würde damit ohne weiteres Zutun
jedes Batch-Update blockieren, solange ein Scan läuft — und umgekehrt.

Der Store bekommt deshalb ein Feld `kind` (`"batch"` | `"discovery"`), und
beide Prüfungen filtern darauf. Discovery hat eine eigene, unabhängige
Exklusivität: ein Discovery-Job zur Zeit. Ein Regressionstest hält genau das
fest.

Store, Lock und `_prune_locked()` bleiben geteilt, `GET /api/jobs/<id>` bleibt
der eine Polling-Endpunkt. Ein zweiter Job-Store mit kopierter Lock-, Prune-
und Snapshot-Logik wäre genau die Duplikation, die in diesem Projekt schon
einmal die CLI gekillt hat.

## Aufbau

Neu ist `app/tasmota/discovery.py` — reine Suchlogik, ohne Flask, ohne
Job-Verwaltung, testbar wie `updater.py`:

| Funktion | Aufgabe |
|---|---|
| `browse_mdns(duration)` | browst `_http._tcp.local.` und `_tasmota._tcp.local.` |
| `scan_network(hosts, *, probe, workers, on_progress)` | Thread-Pool über eine **fertige** Host-Liste |
| `probe_host(ip, timeout)` | `GET http://<ip>/cm?cmnd=Status%200`, ohne Credentials |
| `parse_status(payload)` | IP, Hostname, Friendly Name, Modul, Firmware-Version, MAC |

Im Kern steckt bewusst **keine** Policy. `scan_network()` bekommt Hosts, keinen
CIDR. Die Prüfung „was darf überhaupt gescannt werden" sitzt als
`validate_scan_target()` in der API-Schicht.

Das ist keine Kosmetik: die Policy verbietet Loopback, und ein Kernpfad-Test
muss gegen einen lokalen Stub-Server auf Loopback laufen können. Läge die
Prüfung im Scanner, wäre der einzige ehrliche Test des Scanners unmöglich —
und übrig bliebe ein Test, der `probe_host` mockt und damit nichts beweist.

## Identifikation

Ein Host gilt genau dann als Tasmota, wenn

- HTTP 200 mit JSON, das einen `Status`-Block enthält, oder
- HTTP 401 mit `Need user&password` im Körper.

Alles andere wird verworfen. Ohne diese Strenge landen Drucker, Kameras und
jeder andere HTTP-Sprecher im Netz in der Vorschlagsliste.

Der zweite Fall wird als `requires_auth: true` ausgewiesen — als *Ergebnis*,
nicht als Anlass für einen zweiten Versuch. Siehe Sicherheitsregel 1.

## API

### `GET /api/discovery`

Was die UI zum Vorbelegen braucht:

```json
{
  "suggested_networks": ["192.168.1.0/24"],
  "limits": {"max_prefix": 22, "max_hosts": 1024}
}
```

Die Ermittlung braucht keine neue Dependency: ein UDP-`connect()` auf eine
Dummy-Adresse verrät die eigene Interface-IP, ohne ein Paket zu senden.

### `POST /api/discovery`

```json
{"method": "mdns"}
{"method": "scan", "network": "192.168.1.0/24"}
```

→ `202 {"job_id": "…"}`.
`400` bei abgelehntem Netz, mit der Begründung im Klartext.
`409`, wenn bereits ein Discovery-Job läuft.

### `GET /api/jobs/<id>`

Liefert für Discovery-Jobs zusätzlich `kind`, `method`, `notice` und pro Fund:

```json
{"ip": "192.168.1.42", "hostname": "tasmota-42", "friendly_name": "Flur",
 "module": "Sonoff Basic", "firmware_version": "14.2.0",
 "mac": "AA:BB:CC:DD:EE:FF", "requires_auth": false,
 "already_configured": false}
```

`completed`/`total` tragen den Fortschritt. Bei mDNS bleibt `total` `null` —
die Zahl ist dort nicht bekannt, und eine erfundene wäre gelogen.

`already_configured` markiert IPs, die schon in der Konfiguration stehen.

## Sicherheit

Discovery stellt einen Netzwerk-Scanner hinter die API. Das Zugangs-Gate ist
seit v0.5.0 fail-closed ([#69](https://github.com/dodjango/tasmota-auto-updater/issues/69))
und erbt sich automatisch: Session-Cookie oder `X-API-Key`, und der `POST`
verlangt JSON. Darüber hinaus gelten fünf Regeln, die nicht verhandelbar sind.

1. **Nie Credentials beim Probing** — auch nicht die aus `devices.yaml`. Ein
   Scanner, der gespeicherte Passwörter gegen unbekannte Hosts wirft, ist
   Credential-Spraying. `requires_auth` ist deshalb ein Ergebnis und löst
   keinen zweiten Versuch aus.
2. **`validate_scan_target()`**: nur IPv4, muss `is_private` sein, kein
   Loopback, Link-Local, Multicast oder Unspecified, Präfix ≥ /22. Netz- und
   Broadcast-Adresse werden übersprungen. Ein Scan ins öffentliche Netz ist
   damit strukturell unmöglich, nicht bloß unüblich.
3. **Parallelität (64) und Host-Timeout (1,5 s) sind fest verdrahtet** und über
   die API nicht steuerbar. Ein per Request einstellbarer Parallelitätsgrad
   wäre ein DoS-Knopf hinter der Session.
4. **Kein Retry, `allow_redirects=False`, Response-Körper auf 64 KiB
   begrenzt.** Ein bösartiger Host im LAN darf keinen Worker mit einem endlosen
   Stream festhalten und den Scanner nicht auf ein anderes Ziel umlenken.
5. **Kein Scan läuft automatisch** — auch nicht beim Öffnen des Dialogs. Jeder
   Scan ist ein bewusster Klick auf einen Knopf, der vorher sagt, was er tut.

Logging läuft wie überall über `sanitize_log_data()`. Die Fundliste kann keine
Credentials enthalten, weil nie welche gesendet werden.

Für das Threat-Model ([#74](https://github.com/dodjango/tasmota-auto-updater/issues/74))
fällt hier ein fertiger Abschnitt ab: neue Angriffsfläche „Netzwerk-Scanner
hinter der API" mit den Gegenmaßnahmen 1–5.

## Neue Dependency

`zeroconf`, ausschließlich für mDNS. Vor der Aufnahme läuft der
`dependency-guard`-Check (OSV, Alter, Adoption, Typosquat), wie es die
Projektregel für jedes neue Paket verlangt.

Ist der Import nicht möglich, endet ein mDNS-Job als `error` mit klarer
Meldung — der Scan-Pfad bleibt davon unberührt.

## Frontend

Ein Knopf im Geräte-Editor öffnet ein Modal mit zwei getrennten Aktionen:
„Search via mDNS" (ein Klick, keine Parameter) und „Scan network" (CIDR-Feld,
vorbelegt). Die Oberfläche bleibt Englisch (`<html lang="en">`).

Beide Knöpfe tragen laut Projektkonvention einen Tooltip mit Aktionsverb; der
Scan-Tooltip warnt ausdrücklich, dass eine HTTP-Anfrage an jede Adresse im
angegebenen Netz geht.

Fortschritt: beim Scan ein Balken aus `completed`/`total`, bei mDNS ein Spinner
mit Restzeit. Kein erfundener Balken, wo kein `total` existiert.

Funde erscheinen mit Auswahlkästchen. Bereits konfigurierte Geräte sind
sichtbar, aber deaktiviert und als solche beschriftet; `requires_auth`-Funde
bekommen ein Hinweis-Abzeichen. Die Auswahl fügt ungespeicherte Zeilen in den
Editor ein — gespeichert wird nur über dessen bestehenden Speichern-Knopf und
damit über `PUT /api/config/devices`.

Das Modal zu schließen beendet **nicht** den Serverjob, sondern nur die
Anzeige. Der Knopf heißt deshalb „Close", nicht „Cancel". Ein echtes Abbrechen
wäre zusätzlicher Zustand für höchstens 25 gesparte Sekunden.

Barrierefreiheit: Fokusfalle im Modal, `aria-live` für den Fortschritt,
`data-testid`-Haken für Playwright.

## Fehlerverhalten

| Lage | Verhalten |
|---|---|
| Einzelner Host antwortet nicht | Normalfall, kein Job-Fehler, kein Log-Eintrag pro Host |
| mDNS ohne Treffer | `completed`, leere Liste, `notice`: kein Gerät hat sich angekündigt; im Bridge-Netz-Container kann mDNS grundsätzlich nichts finden |
| Scan ohne Treffer | `completed`, leere Liste, klarer Text |
| `zeroconf` nicht importierbar | `error` mit Klartext-Meldung |
| Netz abgelehnt | `400` mit Begründung, kein Job |
| Discovery-Job läuft schon | `409` |

Der mDNS-Fall ist der wichtigste: „keine Geräte gefunden" wäre dort schlicht
falsch — gefunden wurde nichts, *weil nichts ankommen konnte*. Das gehört zur
selben Ehrlichkeitslinie wie `isVersionComparisonKnown()`
([#91](https://github.com/dodjango/tasmota-auto-updater/issues/91)).

## Tests

- **Unit** `discovery.py`: `parse_status()` gegen echte Fixtures — Tasmota
  `Status 0`, 401-Körper, fremdes JSON-Gerät, kaputtes JSON.
  `validate_scan_target()` als Tabelle über privat/öffentlich/zu groß/Müll.
- **Echter Kernpfad, ungemockt:** `scan_network()` gegen einen lokalen
  HTTP-Stub auf Loopback mit drei Ports — Tasmota, 401, Fremdgerät. `probe_host`
  wird dabei *nicht* gemockt. Genau dieses Mocking hat beim `--force`-Feature
  verborgen, dass der Kern nicht kann, was die Oberfläche versprach
  ([#126](https://github.com/dodjango/tasmota-auto-updater/issues/126)).
- **`jobs.py`:** Regressionstest, dass ein Discovery-Job keinen Batch-Job
  blockiert und umgekehrt.
- **API:** 202/400/409, Zugangs-Gate nach dem Muster aus `test_auth_gate.py`,
  `already_configured`-Markierung.
- **E2E:** Modal, Job per `page.route` gestubbt, Übernahme in den Editor.
  Ein Schreibtest läuft auf einer Kopie von `devices-dev.yaml`, nie auf dem
  Original. Vor dem PR läuft die ganze e2e-Suite — neue Markierung bricht
  bestehende Tests über Playwrights Strict Mode.

## Doku

- `docs/container-setup.md`: zweite Compose-Variante mit `network_mode: host`
  für mDNS, samt ehrlicher Aufstellung, was man dafür aufgibt (Netz-Isolation,
  Port-Mapping).
- `docs/api.md` und Swagger-Docstrings mit Request- und Response-Beispielen.
- `docs/web-interface.md`: der Discovery-Ablauf.
- `docs/configuration.md`: die Grenzen. Es gibt **keine** neue
  Pflicht-Umgebungsvariable.
- `docs/contributing.md`: „Device Discovery" fällt aus den *Areas for
  Improvement*.
- README-Prüfung und `mkdocs build --strict` vor dem PR.

## Restrisiken

- **Der /24-Vorschlag kann falsch sein.** Wer ein /23 fährt, sieht die Hälfte
  seiner Geräte nicht und muss den CIDR korrigieren. Bewusst in Kauf genommen:
  die Präfixlänge ohne neue Dependency zu ermitteln, ist plattformabhängig.
- **mDNS im Bridge-Netz findet nichts.** Kein Fehler, sondern Physik. Die
  Gegenmaßnahme ist Text, nicht Code.
- **Ein Scan erzeugt Last im LAN.** 1024 HTTP-Anfragen sind für ein
  Heimnetz unkritisch, aber nicht null. Deshalb opt-in und nie automatisch.
- **`already_configured` nutzt den Lesepfad** (`load_devices_from_file()`), der
  jeden Fehler mit einer leeren Liste beantwortet. Im schlimmsten Fall gilt ein
  bekanntes Gerät als neu — reine Anzeige, kein Schreibpfad, harmlos.
