# RobotLab demo

Detta är en ny, hårdvaruoberoende startpunkt för den demo som beskrivs i mejltråden **Projekt i RobotLab?** (5 september 2026). Den innehåller tre-i-rad som en konkret första spel-loop och en kalibrerbar simulerad placering av spelpjäser.

Repo:t utför ingen fysisk robotrörelse, ansluter inte till 5G och antar ingen robotmodell. `robotlab.robot` producerar endast approach-, target- och retract-punkter. Det gör att spel- och kommunikationskontraktet kan provas innan RobotLab och Ericsson har bekräftat robot, gripdon, nätverk och driftmiljö.

## Kör

Kräver Python 3.11 eller senare och inga tredjepartspaket.

```text
python -m unittest discover -s tests -v
python -m robotlab demo --output artifacts/demo.json
python -m robotlab play
python -m robotlab serve --port 8765
```

`serve` binder bara till `127.0.0.1`. Läs `GET /health` och `GET /state`. Skicka ett kommando som hämtats från aktuell state till `POST /commands` med `Content-Type: application/json` och exakt `Content-Length`. Exempel:

```json
{
  "protocol_version": 1,
  "command_id": "move-001",
  "session_id": "<från /state>",
  "expected_revision": 0,
  "expires_at_ms": 4102444800000,
  "action": "move",
  "cell": 4
}
```

I riktiga nätet måste deadline ligga högst 30 sekunder framåt enligt serverns klocka; exemplet visar bara formen. `move` placerar fjärrspelarens X, `robot_move` låter den simulerade motspelaren välja O, `stop` låser sessionen och `reset` startar en ny session. `command_id` gör identiska återförsök idempotenta under processens livstid. Ett stopp, en sessionsändring eller en revisionskonflikt ska behandlas som ett säkerhets- och samordningsfall, inte tyst återförsökas.

## Vad som är belagt

Mejlet anger projektperiod september–oktober 2026, WARA-Ops, samarbete med Ericsson, robot uppkopplad via 5G och att RobotLab ansvarar för robotdelen; tre-i-rad anges som exempel. Markus och Fredrik svarade att de vill delta. Robotmodell, spel, pjäsdetektion, API, säkerhetsprocedur och exakt antal timmar är ännu inte fastställda. Se [offentlig research och öppna frågor](docs/research-public.md).

Det tidigare Applied Robotics-repot [`tbergkvist/FRTN85_group8`](https://github.com/tbergkvist/FRTN85_group8) är endast granskat som referens. Ingen kod, modellvikt eller kalibreringsfil är kopierad hit. Referensen visar möjliga framtida integrationsspår (SMC, perception och kalibrering), men den nya kärnan hålls medvetet frikopplad tills hårdvaran och gränssnittet är bekräftade.

## Nästa beslutspunkt

Inför fysisk implementation behöver projektmötet fastställa robot/gripdon, spelvariant, koordinat- och kalibreringsformat, vem som äger kommando- och kvittensprotokollet, samt hur stopp och återanslutning hanteras. Därefter kan en adapter läggas bakom `SimulatedRobot` utan att ändra spellogiken eller protokollets tester.
