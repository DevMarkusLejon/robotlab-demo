# RobotLab demo

## SMC på labbroboten

En separat SMC-väg finns nu för Markos befintliga robotinstallation.
Läs [integrationsplan och labbchecklista](docs/smc-integration.md).
Prova hela kontraktet utan ROS, kamera eller robot:

```text
python -m robotlab.smc_demo --config config/smc-offline.json --game
```

Detta är ett deterministiskt **offline-test**, inte fysiksimulering eller
hårdvaruvalidering. Den befintliga Gazebo-startaren nedan är kvar. SMC-vägen
har ett separat terminalgränssnitt; pek-UI/5G är ännu inte anslutna till den.


## Starta med ett dubbelklick (Windows)

Dubbelklicka på **Starta RobotLab.cmd** i projektmappen, eller på **RobotLab**
på skrivbordet om genvägen finns. Inga terminalkommandon behövs.

Startfönstret startar automatiskt WSL-simulatorn och väntar på roboten och
brädkameran innan webcam-fönstret öppnas. Peka på en ruta och håll kvar cirka
1,2 sekunder. Du spelar röd (X); roboten placerar därefter blå (O).
Ta bort handen mellan dina drag. Spela tills någon vinner eller det blir oavgjort.
**Nytt spel** återställer brädet och pjäserna. **Testa pekning utan robotrörelse**
låter dig kontrollera detektionen separat. Stäng kameran med **Q/Esc** eller kryssknappen.
Stäng startfönstret för att avsluta både kameran och den egna simulatorn.
Att stänga startfönstret avbryter även ett pågående simulerat försök.

Vid fel visas ett meddelande. **Öppna loggar** visar underlag för felsökning.
Startfilen använder den befintliga installationen: Python med webcam-paketen
och handmodellen samt WSL-distributionen `Ubuntu-22.04` med byggd ROS 2-miljö
och gripdonsplugin. Den är en startare för den här datorn, inte ett fristående
installationspaket för andra datorer.

Detta är en ny, hårdvaruoberoende startpunkt för den demo som beskrivs i mejltråden **Projekt i RobotLab?** (5 september 2026). Den innehåller tre-i-rad som en konkret första spel-loop och en kalibrerbar simulerad placering av spelpjäser.

Repo:t utför ingen fysisk robotrörelse och ansluter inte till ett verkligt 5G-nät.
Speldemon använder en UR5e-referens i Gazebo; den fysiska roboten är inte vald.
Den enklare hårdvaruoberoende kärnan i `robotlab.robot` finns kvar separat.

## Det nya spelläget

- Ett helt spel med fem röda och fyra blå pjäser och en optimal motspelare.
- Ett simulerat magasin matar fram en ny pjäs till samma hämtplats. Varje pjäs
  skapas en gång; befintliga pjäser flyttas endast av robot/gripdon/fysik.
  Detta är en förenklad dispenser, inte en modell av ett valt fysiskt magasin.
- Varje drag kräver tre färska kamerabilder med exakt förväntad förändring.
  Tidigare pjäser måste ligga kvar. Brädet uppdateras först efter verifiering.
- Gripdonet väljer en namngiven pjäs bara när det är avstängt och lossat.
  Placerade pjäser finns kvar i MoveIts kollisionsmodell.
- Handen måste vara stabil och tas bort mellan turerna. Inga drag köas medan
  roboten arbetar. Fel låser spelet tills scenen startas om.
- Svensk återkoppling visar grepp, rörelse, kamerakontroll och vinst/oavgjort.

Se [praktiskt handprov](docs/manual-acceptance.md) och
[öppna beslut för fysisk robot och 5G](docs/integration-open.md).
Det implementerade gränssnittet beskrivs i [pekningsprotokollet](docs/live-protocol.md).

## Upprepningsbara systemtester (Windows)

Stäng en eventuell RobotLab-session först. Testverktyget startar och avslutar
sin egen simulator och sparar resultat i `artifacts/acceptance-*.json`.

```text
python -m robotlab.acceptance --game --repeats 2
python -m robotlab.acceptance --cells --repeats 3
python -m robotlab.acceptance --faults
python -m robotlab.metrics artifacts/live-SESSION-ID.jsonl
```

Speltestet skickar syntetiska pekobservationer från Windows. Celltestet placerar
en röd pjäs i varje ruta med ny scen mellan försöken. Feltestet kontrollerar
stopp vid injicerat kamerabortfall och verkligt utebliven gripkontakt i simuleringen.
Resultaten skiljer lyckade placeringar från korrekt avvisade felprov.
Varje körning får egen telemetri i `live-<sessions-id>.jsonl`. Försöks-id kopplar
samman start, kameraevidens, avslut och tidsåtgång; misslyckade försök räknas
med i nämnaren. Saknade mätningar visas som saknade, inte som 100 % lyckat.
Protokollproven skickar även gamla sessioner, dubbletter och för gamla bilder
genom den riktiga lokala HTTP-bryggan samt gör ett uppehåll i bildflödet.
Eventuell rapporterad rundturstid gäller loopback, inte ett 5G-nät.

## Kör

Den enklare spel-/HTTP-kärnan kräver Python 3.11 eller senare och inga
tredjepartspaket. Webcam och ROS-simulering har ytterligare beroenden.

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

Det finns också en äldre, fristående Gazebo Harmonic-värld med en enkel
3-DOF-arm och ett 3×3-bräde. Se [simuleringsguiden](simulation/gazebo/README.md).
Dubbelklicksstartaren använder i stället ROS 2 Humble och Gazebo Fortress i
WSL2 med officiell UR5e-modell, MoveIt och kameraverifierad plockning.

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
UR5e:s officiella kinematik- och ledreferenser ligger i
`simulation/ur5e/ur5e_reference.json`; SDF-geometrin är medvetet lättviktig
fram tills den officiella ROS-beskrivningen kopplas in.

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
