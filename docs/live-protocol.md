# Lokalt gränssnitt för pekning och spelsimulering

Detta dokument beskriver det implementerade gränssnittet på
`http://127.0.0.1:8766`. Det är ett lokalt utvecklingskontrakt, inte ett
Ericsson-API och inte en exponerad tjänst för labbnätet. Det äldre
[spel-/HTTP-kontraktet på port 8765](protocol.md) är en separat kärndemo.

## Läs status innan du skickar en observation

`GET /status` ger bland annat:

| Fält | Betydelse |
| --- | --- |
| `run_id` | Nytt id vid varje scenstart; gamla klienter avvisas |
| `server_time_ms` | Serverns Unix-tid i millisekunder |
| `last_sequence` | Senast behandlade sekvensnummer |
| `mode` | `game`, `pick_place` eller `hover` |
| `board` | Nio rutor med tom sträng, `X` eller `O`; spelbrädet uppdateras efter kamerabekräftelse |
| `busy` | En tur pågår; inga nya drag köas |
| `rearm_required` | Handen måste först tas bort från rutnätet |
| `terminal` | Spelet är slut eller ett fel har låst det |
| `stage`, `message` | Maskinläsbart steg och svensk återkoppling |
| `error_code` | Felkod när ett placeringsförsök misslyckats |
| `winner`, `is_draw` | Slutresultat i spelläget |
| `simulation_only` | Alltid `true` i denna mottagare |

`GET /camera.jpg` ger simulatorns brädkamera som JPEG, eller HTTP 503 om en
aktuell bild saknas. Handkamerans bilder överförs inte via detta gränssnitt.

## Skicka en färsk observation

`POST /intent` med JSON, högst 2048 byte:

```json
{
  "run_id": "id-fran-status",
  "sequence": 42,
  "timestamp_ms": 1789100000000,
  "input_source": "windows_mediapipe",
  "intent": {
    "x": 0.5,
    "y": 0.5,
    "confidence": 0.98,
    "gesture": "point",
    "track_id": 1
  }
}
```

Exemplets id, sekvens och tid ska ersättas med aktuella värden. `x` och `y`
ligger inom 0–1 i handkamerans överlagrade rutnät. Rutor numreras 0–8 radvis;
det svenska gränssnittet visar 1–9. `intent: null` betyder att ingen giltig
pekning finns i rutnätet. `input_source` är frivillig, klientrapporterad metadata
för loggning; det är ingen autentisering eller bevis på mänsklig inmatning.

Klienten läser serverns tid och skattar skillnaden mot sin lokala klocka.
Servern avvisar observationer äldre än 500 ms eller mer än 50 ms i framtiden.
Sekvensnumret ska öka för varje paket. Ingen osäker POST spelas om automatiskt.

Svaret innehåller `stage`, exempelvis `confirming`, `accepted`, `rejected`,
`busy`, `release`, `complete` eller `failed`. En stabil pekning kräver normalt
tolv observationer. Byte av mål, för låg confidence, för gammal observation,
hand som försvinner eller uppehåll längre än 500 ms nollställer bekräftelsen.
Ett accepterat kommando måste hämtas av arbetaren inom sin egen 500 ms-gräns;
senare paket kan inte förlänga den tiden.

## Tur, kvittens och återställning

I spelläget placerar roboten först användarens röda X och därefter sitt blå O.
Varje placering kräver eget kamerakvitto med tre nya bilder. `busy` gäller
hela turen. `board` kan därför visa den bekräftade röda pjäsen medan robotens
motdrag fortfarande pågår. Handen måste tas bort efter turen innan ett nytt
mänskligt drag accepteras. Ett avslutat eller misslyckat spel kan inte återupptas
genom att fortsätta skicka observationer.

Nytt spel görs genom att startaren avslutar den egna simulatorkedjan och skapar
en ny scen och ett nytt `run_id`. Det finns inget fjärrkommando som återställer
eller kringgår ett osäkert utfall. Q/Esc stänger kamerafönstret; skrivbordsstartaren
avslutar då också sin simulator. Detta är inte ett fysiskt nödstopp.

Protokollfel ger HTTP 400 med `error`; exempel är `wrong_server_run`,
`duplicate_or_old_frame` och `stale_or_future_frame`. Ett utförandefel rapporteras
i status med `stage: failed`, `terminal: true` och en felkod. Den senaste säkert
kamerabekräftade brädställningen behålls tills scenen startas om.

Inför 5G ska transport, åtkomst, klockhantering, deadline och ansvar för lokal
stoppfunktion förankras med Ericsson/labbet. Se [öppna integrationsbeslut](integration-open.md).
