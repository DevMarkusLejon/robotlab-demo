# Kommando- och säkerhetskontrakt (version 1, simulator)

Kontraktet är ett förslag som gör ansvarsfördelningen mellan fjärrspelare och robotkod testbar. Det är inte en färdig Ericsson-integration och ska granskas innan det används utanför loopback-simulatorn.

## State

`GET /state` returnerar `session_id`, monotont `revision`, bräde, `next_player`, `winner`, `legal_moves`, `stopped` och `simulation_only: true`. En klient ska läsa state precis före varje kommando. `revision` ökar efter ett accepterat kommando.

## Commands

Alla POST-kommandon måste vara ett enda JSON-objekt med unika fält, känd `protocol_version: 1`, `command_id`, `session_id`, `expected_revision`, `expires_at_ms` och `action`. `move` har dessutom `cell` (0–8). `command_id` är 1–64 tecken (`A-Z`, `a-z`, siffror, `_`, `-`). Body är högst 8192 byte.

Åtgärderna är:

| action | Effekt |
| --- | --- |
| `move` | Validerar och simulerar X på angiven ruta. |
| `robot_move` | Väljer och simulerar O med den deterministiska boten. |
| `stop` | Latched mjukvarustopp; kan inte hävas med nya drag. |
| `reset` | Rensar simulatorn och skapar ett nytt sessions-id. |

Samma `command_id` och exakt samma payload returnerar samma receipt utan ett nytt drag. Samma id med annan payload returnerar konflikt. Revisions-, sessions- och deadlinefel returneras före spelmutation. Ett placeringsfel latched fault och stoppar simulatorn; ett osäkert fysiskt utfall ska aldrig blindt återförsökas.

## HTTP-fel

`400` används för ogiltigt JSON/kommando, `408` för utgången deadline, `409` för state-, tur-, drag- eller id-konflikt, `413` för för stor body, `415` för fel Content-Type och `503` när receipt-cachen är full. Fel innehåller `error`, `message` och aktuell state när den kan läsas.

## Medvetna begränsningar

HTTP-servern binder lokalt, använder ingen autentisering, TLS, replay-skydd mellan processstarter eller fysisk nödstopp. Den får därför inte exponeras på labbnätet. 5G-latens och reconnect-policy ska mätas och beslutas med Ericsson-teamet; `expires_at_ms` är en säkerhetsgräns, inte ett påstående om uppnåelig latens.
