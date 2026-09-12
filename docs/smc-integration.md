# SMC-integration: plan, implementation och labbdriftsättning

Datum: 2026-09-12. Markus har bekräftat att Markos SMC-lösning används på den
robot som projektet kommer att använda. Vi utgår därför från SMC och labbets
faktiska uppställning. Gazebo är en befintlig referens, inget krav på arkitekturen.

## Målet och vad som är genomfört

Första fysiska milstolpe: välj en ruta → hämta en pjäs → placera → dra tillbaka
→ verifiera med den fysiska kameran → uppdatera spelet.

Implementerat i denna ändring:

- Ett robotoberoende `PlacementService` med samma tre-i-rad-regler och solver.
- Inlärda ledvägar, separat för nio hämtplatser och nio brädrutor.
- `SMCRobot` som använder SMC:s `moveJPWTraj(..., run=False)` och
  `ControlLoopManager.run_one_iter` med deadline, tillståndskontroll, stopp och
  uppmätt slutposition. Ingen ny hastighetsregulator har skrivits.
- En referensfabrik för den granskade SMC-versionen och Robotiqs socketprotokoll.
  Annat gripdon kräver en labbspecifik fabrik med samma kontrakt.
- Kontinuerligt läst fysisk kamera med den befintliga färgdetektorn, fyrpunkts-
  kalibreringen och handdetektorn. Tre färska bildobservationer krävs.
- Terminalkörning av en placering eller helt spel. Det befintliga pekgränssnittet
  och 5G är ännu INTE kopplade till SMC-terminalen.
- Offline-fixtures som kör hela kontraktet, men inte modellerar robotfysik.
  Deras resultat räknas aldrig som lyckade kameraverifierade robotplaceringar.
- Tester för kvittenser, gamla sessioner, återförsök, fel, gripdon och SMC-adapter.

Ingen fysisk robot har anslutits eller körts här. Full SMC med Pinocchio/RTDE
har inte körts i denna miljö. Adaptertesterna använder testdubblar. Utvald
kameradrivrutin, labbets SMC-installation och verkliga robotrörelser måste provas
på plats innan integrationsarbetet kan kallas hårdvaruvaliderat.

## 1. Fastställ den befintliga installationen

Granskad upstream-version:
`4efe7bbb00f8e39c72e3a3fd21f2f1f4ded0f0f1`.

Källor:

- [SMC README](https://gitlab.control.lth.se/marko-g/ur_simple_control/-/blob/4efe7bbb00f8e39c72e3a3fd21f2f1f4ded0f0f1/README.md)
- [UR5e RobotManager](https://gitlab.control.lth.se/marko-g/ur_simple_control/-/blob/4efe7bbb00f8e39c72e3a3fd21f2f1f4ded0f0f1/python/smc/robots/implementations/ur5e.py)
- [Joint-space-regulatorer](https://gitlab.control.lth.se/marko-g/ur_simple_control/-/blob/4efe7bbb00f8e39c72e3a3fd21f2f1f4ded0f0f1/python/smc/control/joint_space/joint_space_point_to_point.py)
- [ControlLoopManager](https://gitlab.control.lth.se/marko-g/ur_simple_control/-/blob/4efe7bbb00f8e39c72e3a3fd21f2f1f4ded0f0f1/python/smc/control/control_loop_manager.py)

Med Marko, notera robotens serienummer, installerad SMC-commit och eventuella
lokala ändringar, Python-/ur_rtde-version, gripdonets modell, TCP, payload,
anslutningssätt och fungerande start-/stopprutin. Upstream-versionen är inte
automatiskt samma som labbets. Referensfabriken avvisar annan eller modifierad
SMC-version; granska skillnaderna och uppdatera kompatibilitetsreferensen om
labbet använder en annan version. Byt inte labbets fungerande installation för
att passa denna kod.

Konkreta upstream-beteenden att gå igenom:

- RobotManager-konstruktorn ansluter och sätter speed slider till 1.0. Den är
  inte ett read-only-anrop. Våra lägre max_v_percentage/acceleration begränsar
  kommandona separat, men är inte en validerad säkerhetsfunktion.
- `stopRobot()` använder speedStop, stopJ och en kort freedriveövergång.
  Referensfabriken använder detta befintliga stopp och kontrollerar därefter
  ett nytt RTDE-sample med låg ledhastighet. Beteendet måste passa uppställningen.
- Upstream kan aktivera/autokalibrera gripdonet i konstruktorn. Vår fabrik
  ansluter roboten med `gripper='none'`, ansluter gripdonet separat och kräver
  att det redan är aktiverat via labbets rutin.
- SMC:s banfunktion avslutar efter sin beräknade tid. Vår adapter verifierar
  faktiskt uppmätt ledposition och hastighet efter stopp; tidsutgång är inte
  en framgångskvittens.

## 2. Lär in arbetscellen, utan simuleringskoordinater

Kopiera `config/smc-lab.template.json` till en egen lokal konfiguration och fyll
alla tomma värden. Mallen är medvetet ogiltig tills uppställningen är inmätt.
Den innehåller inga antagna robot-IP, serienummer eller hårdvarupositioner.

| Fält | Innehåll |
| --- | --- |
| `home` | Sex uppmätta ledvinklar i radianer vid gemensam fri transitposition |
| `joint_limits` | Sex överenskomna ledintervall för denna arbetscell |
| `sources[0..8]` | Vägar från home till respektive pjäs; sista punkten är grepposition |
| `cells[0..8]` | Vägar från home till respektive ruta; sista punkten är släpposition |
| `robot_serial`, `tool_id`, `calibration_id` | Identifiering av den faktiska uppställningen |
| `routes_reviewed_by` | Vem som provat hela vägsträckorna i labbet |
| `smc_connection_and_stop_reviewed_by` | Vem som gått igenom anslutnings- och stoppbeteendet |
| `smc` | Labbdatorns IP-/gripdons-/hastighetskonfiguration |

En väg måste innehålla minst approach och kontakt/släpp. Mellan dem får flera
inlärda mellansteg finnas. Efter grepp/släpp följs vägen baklänges till home.
Robotens start måste redan vara vid home; programmet gör ingen blind hemkörning.

Hämtplatserna används i turordning: röd, blå, röd, blå, röd, blå, röd, blå, röd.
De innehåller fem röda och fyra blå pjäser. Varje pjäs används en gång per spel.
Ingen fysisk dispenser antas och ingen pjäs återskapas i hårdvaruvägen.

Inlärda ledpunkter är INTE en kollisionskontrollerad bana. SMC interpolerar
mellan dem i ledrymd, vilket inte behöver ge en rak TCP-bana. Prova hela banorna,
inklusive omvända sträckor, med rätt verktyg och buren pjäs samt pjäser på brädet.
Lägg till mellansteg där det behövs. Flaggan
`paths_checked_with_payload_and_all_board_states` dokumenterar den kontrollen;
den utför ingen automatisk kollisionskontroll. Rörliga hinder hanteras inte.

Framgångskriterium: varje source-/cellväg går att genomföra lokalt med den valda
SMC-funktionen, utan att stöta i bord, verktyg, pjäser eller roboten själv.

## 3. Kamera och kvittens

Använd samma röda/blå runda pjäser som färgdetektorn stödjer. Kalibrera fyra
hörn i ordningen övre vänster, övre höger, nedre höger, nedre vänster sett från
kameran. Rutorna 0–8 räknas radvis i den bilden. Inlärda robotrutor måste använda
samma numrering, även om roboten ser brädet från motsatt håll.

Kamerafilen har formatet:

```json
{"corners_px": [[100,100], [700,100], [700,700], [100,700]]}
```

Dessa siffror visar ENDAST formatet; mät dina egna pixlar.

Prova befintligt manuellt observationsverktyg först:

```text
python -m robotlab.observe_board --calibration camera.json --cell 4 --symbol X
```

Kontrollera båda färgerna i alla nio rutor, samt hand över brädet, fel ruta och
utebliven bild. Detektorn är färg-/formbaserad och upptäcker inte automatiskt
kalibreringsdrift. Bildtiden sätts när datorn tar emot bilden; kamerans interna
buffring måste kontrolleras på den valda kameran. En blockerad läsning får timeout
i konsumenten men stoppar inte en eventuell blockerad kameradrivrutin med tvång.

Kameran kör hela tiden och måste ha färska data. Baslinjen ska motsvara det
committade brädet. Felaktig, tvetydig eller gammal observation får inte ändra
spelet. Hårdvarukvitton märks `physical_board_camera`; Gazebo- och offlinekvitton
avvisas i det fysiska spelet. Källnamnen är interna kontrakt, inte autentisering.

## 4. Kör ett fysiskt försök

Använd labbets befintliga SMC-miljö, med repo:t tillgängligt i samma Python-miljö.
Installera kameraberoendena vid behov med `pip install -e '.[webcam]'`.

Kontrollera arbetscellsfilen utan import av SMC, nätverksanslutning eller rörelse:

```text
python -m robotlab.smc_demo --backend smc --config config/smc-lab.json --check-config
```

Kontrollen validerar struktur och markeringar, inte att inmätningen är korrekt.
När labbuppställningen är redo, kör en placering:

```text
python -m robotlab.smc_demo --backend smc --config config/smc-lab.json --factory robotlab.smc_lab:connect --camera-calibration camera.json --cell 4 --execute
```

Referensfabriken gäller endast ett uttryckligen valt `robotiq_socket`-gripdon,
med faktiskt bekräftad port. SMC har även RS485/OnRobot-alternativ; för dem behövs
en annan fabrik `module:function` som returnerar `SMCRobot` med motsvarande
`open_and_confirm`, `close_and_confirm_object`, `object_held`, status och stopp.
Gripdonstypen på projektroboten är ännu inte bekräftad i underlaget.

Samma kommando med `--game` i stället för `--cell 4` kör ett spel: människan anger
X-rutan i terminalen, solvern väljer O. Programmet stannar efter vinst/oavgjort.
Före ett nytt spel återställs brädet/pjäserna fysiskt enligt labbrutinen och en ny
session startas. Efter fel krävs alltid fysisk kontroll; ett nytt command-id
räcker inte för att fortsätta. Grippern öppnas inte automatiskt vid fel eftersom
roboten kan hålla en pjäs. Lokal nödstoppfunktion är robotens, inte Pythonkodens.

Ordning på plats:

1. Jämför ledåterkoppling och TCP med teach pendant, i samma bas-/verktygsram.
2. Prova rörelser ovanför brädet enligt labbrutinen, utan pjäs.
3. Prova grepp, lyft, släpp och gripdonets verkliga återkoppling separat.
4. En placering i ruta 4 med kamerakvittens. Kontrollera logg och fysisk ruta.
5. Alla nio rutor med tomt bräde mellan försöken.
6. Helt spel, även med tidigare pjäser kvar som hinder.
7. Prova fel/avbrott enligt labbrutinen och verifiera stillastående robot.

## 5. Koppla pekning och Ericsson efter lokal verifiering

Det nya anropskontraktet är:

```python
service.place(session_id=service.session_id, command_id="move-unique-id",
              expected_revision=service.revision, cell=4)
```

Integrationen för pek-UI/5G ska återanvända det efter intent-/ålderskontroll.
Samma command-id och innehåll returnerar tidigare kvittens utan ny rörelse;
ändrat innehåll under samma id avvisas. Felaktig revision/session avvisas. Inga
kommandon köas medan roboten arbetar. Kvittens betyder kamerabekräftad placering,
inte bara att ett rörelsekommando har tagits emot.

Detta är för närvarande ett lokalt Python-API och ett terminalprogram, ingen ny
nätverkstjänst. Lägg SMC-loopen på labbdatorn nära roboten. Kom överens med Ericsson
om transport, åtkomst, tidsbudget och avbrottsbeteende innan API:t exponeras.

## Offlinekörning och vad testerna bevisar

Verifierat här: **117 tester, 0 fel, 0 överhoppade**. Ett fullständigt offline-spel
med nio kontraktsplaceringar passerade. Se [verifieringsrapport](smc-validation-2026-09-12.json).

```text
python -m robotlab.smc_demo --config config/smc-offline.json --game
python -m robotlab.smc_demo --config config/smc-offline.json --cell 4 --fault grasp
python -m unittest tests.test_smc_integration -v
python -m unittest discover -s tests -v
```

Offlinekörningen provar tillståndsövergångar och det gemensamma gränssnittet med
syntetiska ledpositioner och brädobservationer. Den provar INTE Pinocchio,
verklig RTDE, bildperception, robotfysik, kollisionsfrihet eller 5G. Fullständiga
spel i Gazebo från tidigare arbete är separat evidens. Slå inte ihop dem med
SMC:s offlinekörningar till en hårdvarusuccess-rate.
