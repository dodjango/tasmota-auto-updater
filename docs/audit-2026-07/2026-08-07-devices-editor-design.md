# Design: Geräte-Editor im Browser

Stand 2026-08-07. Erster von zwei Zyklen zu [#99](https://github.com/dodjango/tasmota-auto-updater/issues/99).
Der zweite Zyklus — Netzwerk-Discovery — bekommt eine eigene Spec, sobald der
Editor steht.

## Ziel und Abgrenzung

Die Geräteliste in der Web-UI pflegen, statt `devices.yaml` per SSH zu
editieren. Anlegen, Ändern, Löschen.

Nicht Ziel: Discovery, Gerätegruppen, Import/Export, Mehrbenutzer-Betrieb,
Historie der Änderungen.

**Eine verbreitete Annahme vorab korrigiert:** ein Neustart des Containers ist
für Konfigurationsänderungen heute schon nicht nötig. `api.py:73` und `:139`
rufen `load_devices_from_file()` bei *jedem* Request neu auf, es gibt keinen
Cache. Der Wert des Editors liegt also nicht im Wegfall des Neustarts, sondern
darin, dass kein SSH mehr nötig ist, dass vor dem Speichern validiert wird, und
dass Discovery-Funde später irgendwo landen können.

## Getroffene Entscheidungen

Diese vier hat der Betreiber entschieden; sie sind die Grundlage von allem
Weiteren.

| Frage | Entscheidung |
|---|---|
| Was ist die Wahrheit? | **Die YAML-Datei.** Keine Datenbank. Handarbeit per SSH bleibt jederzeit möglich. |
| Gleichzeitige Änderungen? | **Letzter Schreiber gewinnt**, keine Konflikterkennung. Bewusst in Kauf genommen. |
| Passwörter? | **Nur schreibbar, nie lesbar.** Leeres Feld heißt „behalten", ein Knopf entfernt das Passwort. |
| Deployment? | **Verzeichnis-Mount** statt Datei-Mount. Breaking Change, dokumentiert. |

Zum zweiten Punkt: ein atomarer Schreibvorgang mit Backup der Vorgängerversion
ist trotzdem vorgesehen. Das ist keine Konflikterkennung — es macht eine
überschriebene Datei nur wiederherstellbar.

## Warum der Editor eine eigene Ressource bekommt

`/api/devices` ist die **operative** Sicht und für den Editor unbrauchbar:

- Es maskiert das Passwort zu `'********'` — ein Wert, der zurückgeschrieben das
  echte Passwort zerstören würde.
- Es überschreibt `dns_name` mit dem *aufgelösten* Namen, und wenn keiner
  auflösbar ist, **mit der IP selbst** (`api.py:80-84`). Ein Round-Trip dieser
  Antwort schriebe `dns_name: 192.168.8.191` in die Konfiguration jedes Geräts,
  das gar keinen Namen hat.

Der Editor bekommt deshalb `/api/config/devices` mit den **rohen konfigurierten**
Feldern. `/api/devices` bleibt unverändert, damit weder die bestehende UI noch
die dokumentierte API brechen.

## API

### `GET /api/config/devices`

Liefert die Konfiguration, wie sie in der Datei steht — ohne DNS-Auflösung, ohne
Anreicherung:

```json
{
  "devices": [
    {"ip": "192.168.8.191", "username": "admin", "has_password": true,
     "dns_name": "flur", "timeout": 240}
  ],
  "writable": true,
  "devices_file": "/app/config/devices.yaml"
}
```

`has_password` ist ein Boolean; das Passwort selbst verlässt den Server nie.
`writable` sagt der UI, ob der Speichern-Knopf überhaupt aktiv sein darf.

### `PUT /api/config/devices`

Ersetzt die Liste. Der Body ist `{"devices": [...]}`.

Eine Teil-Update-Semantik gibt es bewusst nicht: bei „YAML ist die Wahrheit" und
„letzter Schreiber gewinnt" ist das Ersetzen der ganzen Liste die ehrlichste
Form, und die UI hält die Liste ohnehin komplett.

Antworten: `200` mit der neuen Liste, `400` bei Validierungsfehlern, `409` wenn
das Verzeichnis nicht schreibbar ist, `415` wenn der Body kein JSON ist. Die
JSON-Pflicht wird in der Ressource selbst geprüft, wie in `api.py:318` und
`:448` — sie ist im Projekt nicht global.

Zugriffsschutz: `/api/*` ist seit v0.5.0 fail-closed (UI-Session-Cookie oder
`X-API-Key`), es braucht nichts Zusätzliches.

## Die Merge-Regel

**Der Server schreibt nicht, was der Client schickt.** Er liest die Datei, führt
pro Gerät die verwalteten Felder über den bestehenden Eintrag und schreibt das
Ergebnis. Identität ist die IP.

Verwaltete Felder: `ip`, `username`, `password`, `dns_name`, `timeout`.

Das löst vier Dinge mit einer Regel:

1. Das Passwort bleibt erhalten, wenn der Client keins schickt.
2. `fake` und `firmware_info` in `devices-dev.yaml` überleben, obwohl der Editor
   sie nicht kennt.
3. Felder, die eine spätere Version einführt, gehen nicht verloren.
4. Ein Gerät, das im Payload fehlt, wird gelöscht — das ist die einzige Art zu
   löschen, und sie ist explizit.

**Konsequenz, die in die UI gehört:** wird die IP eines Geräts geändert, gilt es
als neues Gerät. Das Passwort lässt sich nicht mehr zuordnen und muss neu
eingegeben werden.

### Passwort-Übergabe

| Client schickt | Wirkung |
|---|---|
| kein `password`-Feld | bestehendes Passwort bleibt |
| `password: "neu"` | wird ersetzt |
| `remove_password: true` | Passwort wird gelöscht |

`remove_password` ist ein reines Steuerfeld und landet nie in der Datei.

## Validierung

Marshmallow, wie im Rest des Projekts, mit `unknown = RAISE`:

| Feld | Regel |
|---|---|
| `ip` | Pflicht, geprüft über das vorhandene `is_valid_ip_address()` |
| `username` | optional, String |
| `password` | optional, String, nur schreibend |
| `dns_name` | optional, String |
| `timeout` | optional, Integer 60–600 (wie `DeviceUpdateSchema`) |

Zusätzlich: **doppelte IPs werden abgelehnt** — dieselbe Regel, die die CLI in
`main()` zieht, aus demselben Grund (zwei Einträge mit derselben IP kollabieren
in jeder IP-basierten Zuordnung).

`fake` und `firmware_info` sind **nicht setzbar**. `unknown = RAISE` lehnt sie
ab. Grund: wer ein echtes Gerät zum Fake-Gerät erklären kann, bekommt frei
erfundene Erfolgsmeldungen — eine Lüge, die genau die Sorte ist, gegen die das
Projekt sonst überall absichert.

`is_valid_ip_address()` blockt bewusst Loopback, Link-local und die
Metadata-Adresse 169.254.169.254. Diese Sperre bleibt: der Editor darf keine
Adressen in die Konfiguration schreiben, die die SSRF-Absicherung der
Update-Endpunkte umgehen würden.

## Schreibpfad

Neues Modul `app/tasmota/config_writer.py`, eine Verantwortung: die Gerätedatei
sicher ersetzen.

1. Schreibbarkeit feststellen (siehe unten — es reicht nicht, das Verzeichnis zu
   prüfen).
2. Temp-Datei **im selben Verzeichnis** schreiben, `flush()` + `os.fsync()`.
3. Bestehende Datei nach `<name>.bak` kopieren.
4. `os.replace(temp, ziel)` — atomar innerhalb desselben Dateisystems.

Schritt 2 muss im selben Verzeichnis passieren, sonst ist `os.replace()` ein
Kopiervorgang über Dateisystemgrenzen und nicht mehr atomar.

Das Backup hält **eine** Generation: jedes Speichern überschreibt `<name>.bak`.
Mehr wäre eine Versionierung, und die gehört nicht in dieses Feature.

### Schreibbarkeit richtig feststellen

`os.access(verzeichnis, os.W_OK)` allein genügt **nicht**. Beim alten
Datei-Mount ist `/app` sehr wohl schreibbar — nur die Zieldatei selbst ist ein
Mountpoint, und `os.replace()` darüber scheitert erst im Moment des Speicherns
mit `EBUSY`. Die API meldete dann `writable: true` und liefe hinterher in einen
Fehler.

Die Prüfung ist deshalb zweiteilig:

```python
writable = os.access(target.parent, os.W_OK) and not target.is_mount()
```

`Path.is_mount()` erkennt den Datei-Bind-Mount, weil sich `st_dev` von Datei und
Elternverzeichnis unterscheiden. Beide Bedingungen müssen erfüllt sein, sonst
ist der Editor schreibgeschützt — und zwar bevor der Benutzer etwas eintippt,
nicht danach.

**Warum das Verzeichnis gemountet sein muss:** ein Bind-Mount auf eine *Datei*
macht diese Datei zum Mountpoint, und ein `rename()` darüber scheitert mit
`EBUSY`. Mit dem bisherigen `./devices.yaml:/app/devices.yaml` funktioniert der
Schreibpfad also nicht. Deshalb der Wechsel auf ein Verzeichnis-Mount.

Erkennt der Writer ein nicht schreibbares Ziel, meldet er das als klaren Fehler.
Die UI zeigt den Editor dann schreibgeschützt mit dem Hinweis, wie man auf ein
Verzeichnis-Mount umstellt — kein Traceback, kein stiller Fehlschlag.

## Frontend

Alpine, wie der Rest der UI. Eine Geräteliste mit Bearbeiten, Hinzufügen,
Löschen und **einem** Speichern-Knopf für die ganze Liste.

Nach den Projektkonventionen: jedes interaktive Element bekommt einen Tooltip,
der mit einem Verb beginnt; das Löschen bekommt zusätzlich eine Bestätigung und
eine Warnung im Tooltip. Bedienbarkeit per Tastatur und Screenreader-Ansage
gehören dazu, nicht als Nacharbeit.

Ist `writable` falsch, sind alle Bedienelemente deaktiviert und ein Hinweis
erklärt warum.

## Tests

- **Unit** für `config_writer`: atomarer Ersatz, Backup entsteht, nicht
  schreibbares Verzeichnis wird erkannt, Temp-Datei landet im Zielverzeichnis.
- **Unit** für die Merge-Regel: Passwort bleibt/wird ersetzt/wird entfernt;
  `fake` und `firmware_info` überleben; fehlendes Gerät wird gelöscht;
  IP-Änderung erzeugt ein neues Gerät ohne Passwort.
- **Unit** für die Validierung: ungültige IP, Loopback, doppelte IPs,
  `timeout`-Grenzen, `fake` wird abgelehnt.
- **Integration** über den Flask-Test-Client: `GET` maskiert, `PUT` schreibt,
  `415` ohne JSON, `409` bei nicht schreibbarem Ziel.
- **E2E** (Playwright): Gerät anlegen, ändern, löschen, speichern, Seite neu
  laden und den Stand wiederfinden.

Keine neuen pytest-Marker.

## Doku

`compose.example.yml` auf das Verzeichnis-Mount umstellen,
`docs/configuration.md` und `docs/container-setup.md` entsprechend, README-Check
nach Projektregel. Ein **Migrationshinweis** gehört in die Release-Notes: wer
`./devices.yaml:/app/devices.yaml` mountet, muss umstellen, sonst bleibt der
Editor schreibgeschützt.

Zwei Verhaltensweisen gehören ausdrücklich in die Doku, weil sie überraschen:
Kommentare in der YAML gehen beim Speichern über die UI verloren, und eine
geänderte IP verlangt das Passwort neu.

## Restrisiken

- **Letzter Schreiber gewinnt** ist eine bewusste Entscheidung, kein Versehen.
  Wer parallel per SSH und über die UI editiert, verliert eine der beiden
  Änderungen. Das Backup macht sie wiederherstellbar, nicht sichtbar.
- **Klartext-Passwörter in der Datei** bleiben, wie sie sind. Der Editor
  verschlechtert das nicht, aber er macht die Datei zum Ziel eines
  Schreibzugriffs über HTTP — im LAN ohne TLS ist das ein Restrisiko, das ins
  Threat-Model (#74) gehört.
- **Kein Audit-Log.** Wer wann welches Gerät geändert hat, ist nicht
  nachvollziehbar. Für einen Einzelbetreiber vertretbar.
