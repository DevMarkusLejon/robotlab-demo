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
python -m pip install -e ".[webcam]"
python -m robotlab download-model
python -m robotlab webcam
```

`serve` binder bara till `127.0.0.1`. Läs `GET /health` och `GET /state`. Skicka ett kommando som hämtats från aktuell state till `POST /commands` med `Content-Type: application/json` och exakt `Content-Length`. Exempel:

## Webcam-exempel

Installera webcam-tillägget och kör `python -m robotlab webcam`. Ett fönster visar kamerabilden och ett virtuellt bräde. Håll upp pekfingret så att fingertoppen ligger över en tom ruta i ungefär tolv bildrutor; då spelar du X. Den simulerade roboten svarar som O. Tryck Q eller Escape för att avsluta.

Webcamläget använder MediaPipes förtränade Hand Landmarker-modell. Den använder handens 21 landmärken och pekfingrets fingertopp (landmark 8), så ansikte och huvud används inte för positionsspårning. En enkel geometriheuristik kräver att pekfingret är utsträckt och klassar övriga observationer som `unknown`; därefter måste samma mål passera `IntentGate` med confidence- och stabilitetskrav innan spelet accepterar ett drag. Modellen laddas ner med `python -m robotlab download-model` från den officiella MediaPipe-modellservern. Bilderna analyseras lokalt och skickas inte över nätet. Detta gör ingen säkerhetsbedömning och driver ingen fysisk robot. Anpassa belysning och `--stable-frames` vid behov.

## Gazebo-simulering

Det finns också en fristående Gazebo Harmonic-värld med en enkel 3-DOF-arm och ett 3×3-bräde. Den är ett konkret nästa steg från webcam-detektion till inspekterbar robotplanering: kör `simulation/gazebo/world.sdf` och styr sedan armen med `simulation/gazebo/play_demo.py`. Se [simuleringsguiden](simulation/gazebo/README.md) för WSL2-kommandon och cellnumrering. Den lokala Windows-miljön har inte Gazebo installerat, så XML och IK är validerade här men själva GUI-körningen behöver Gazebo i WSL2 eller Linux.

## UR5e-referens och säker körkedja

Den mer realistiska vertikala skivan finns i [simulation/ur5e](simulation/ur5e). Den använder en sexledad UR5e-referensmodell, ett overhead-kamerasensorgränssnitt, en separat målplanerare, en säkerhetsgate för ledgränser/hastighet, simulerad nätverksfördröjning/paketförlust och JSONL-telemetri. [dashboard.html](simulation/ur5e/dashboard.html) visar samma steg som en säljdemo. Kör `gz sim simulation/ur5e/world.sdf` och därefter `python3 simulation/ur5e/ur5e_demo.py --cell 4` i WSL2. Perception och hårdvaruadapter är avsiktligt separerade från exekveringen så att vi kan byta in riktig kamera, MoveIt 2 och `gz_ros2_control` när robot och ROS-miljö är bekräftade.

ROS 2/MoveIt 2-handoffen finns i [simulation/ros2_ws](simulation/ros2_ws): där
ligger controller-kontraktet med samma sex lednamn som säkerhetsgaten använder.
För en fysisk bordskamera finns dessutom en fyrpunkts-perspektivkalibrering i
`robotlab.calibration` och ett exempel i
`simulation/ur5e/calibration.example.json`.
Den fulla demo-kedjan kan köras med
`python3 simulation/ur5e/shared_autonomy_demo.py --cell 4 --settle 1.2`;
den demonstrerar intent → nätverk → safety → exekvering i en enda telemetryfil.

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
