# RobotLab, WARA-Ops och befintligt robotprojekt

Kontrollerat 2026-09-06. Underlaget bygger på offentliga förstahandskällor samt det befintliga kursrepo som användaren pekat ut. Detta dokument styrker bakgrund, befintlig kod och möjliga integrationsvägar. Det fastställer inte vilken robot, nätkonfiguration eller programversion som ska användas i den nya demonstrationen.

## Det som påverkar arbetet nu

1. Det finns redan ett relevant schackprojekt: [tbergkvist/FRTN85_group8](https://github.com/tbergkvist/FRTN85_group8), granskat på commit `3e7b6728a64da36f6a21f01c5541ee840fa6d6b1`. Det använder Python och SMC för robotrörelser, RealSense/YOLO för perception och python-chess/Stockfish för spel. Det är därför en bättre integrationsreferens än ett antaget nytt ROS-system.
2. SMC finns offentligt: [Simple Manipulator Control](https://gitlab.control.lth.se/marko-g/ur_simple_control). RobotWiki länkar till detta från sin UR5e-sida. Biblioteket stödjer verkliga och simulerade robotar, men kursprojektet låser ingen SMC-version. API-kompatibilitet behöver därför kontrolleras innan fysisk integration.
3. Ett privat 5G-nät från Ericsson vid Lund RobotLab är dokumenterat i [WASP:s impactrapport 2025, PDF-sida 18](https://wasp-sweden.org/wp-content/uploads/2025/05/waspimpact-250516a-webb.pdf#page=18). Det bekräftar infrastrukturen, men ger inga användbara uppgifter om den nya demonstrationens adresser, fördröjning, tjänstekvalitet eller driftsättning.
4. Spelregler, explicita kommandon, kalibrering, planering, simulering och mätning av kommandoöverföring går att utveckla separat. Val av drivrutin, verkliga gripmått och nätanslutning behöver bygga på labbets aktuella konfiguration.

## Det befintliga kursprojektet

Användarens repo är ursprunget till [Markus fork](https://github.com/DevMarkusLejon/FRTN85_group8MarkusCook). GitHub anger att forken senast pushades 2025-10-17 och ursprungsrepot 2025-10-23. Ursprungskodens senaste granskade commit används därför som referens här. Koden har lästs statiskt; ingen robotkod, modellfil eller notebook har körts.

| Del | Vad koden faktiskt gör | Lämplig fortsättning |
| --- | --- | --- |
| [project_plan.md](https://github.com/tbergkvist/FRTN85_group8/blob/3e7b6728a64da36f6a21f01c5541ee840fa6d6b1/project_plan.md) | Stegar från förflyttning mellan givna koordinater till kameraidentifierade pjäser och fler pjäser. | Använd samma stegvisa upplägg för att återansluta hårdvaran. |
| [robotchess3.py](https://github.com/tbergkvist/FRTN85_group8/blob/3e7b6728a64da36f6a21f01c5541ee840fa6d6b1/robotchess3.py) | SMC `getRobotFromArgs`, kartesisk `moveL`, Pinocchio `SE3`, öppna/stäng gripdon och stoppa robot. FEN/UCI, fångst och rockad samt en Stockfish-loop. | Dela upp spellogik, rörelseplan och hårdvaruadapter; behåll felhantering och verifierad status mellan stegen. |
| [cali.py](https://github.com/tbergkvist/FRTN85_group8/blob/3e7b6728a64da36f6a21f01c5541ee840fa6d6b1/cali.py) | Samlar RealSense-/robotpunktpar, löser rigid transform med SVD, transformerar brädets hörn. `H.txt` och `corners.txt` skrivs med NumPy `tofile`, alltså binära flyttal trots filändelsen. | Gör filformat, enhet, hörnordning, koordinatsystem och kalibreringsfel explicita. Befintliga filer saknas i granskad Git-tree. |
| [computer_vision.py](https://github.com/tbergkvist/FRTN85_group8/blob/3e7b6728a64da36f6a21f01c5541ee840fa6d6b1/computer_vision.py) | Ultralytics YOLO och RealSense; detekterar pjäser, använder djup och deprojekterar bildpunkter till meter. | Introducera en observationsmodell med tidsstämpel, säkerhet och ogiltigt djup. Pröva med inspelade observationer före kameraanslutning. |
| [StockFishing.py](https://github.com/tbergkvist/FRTN85_group8/blob/3e7b6728a64da36f6a21f01c5541ee840fa6d6b1/StockFishing.py) | Lokal UCI-process via python-chess; söker Stockfish via miljövariabel eller PATH. | Kan isoleras som valfri schackmotor. En motor behövs inte för att testa transport eller pick-and-place. |

`robotchess3.py` anger gripdonet `onrobot`, men inget entydigt robotmodellval i den egna argumentfunktionen. Robotvalet delegeras till SMC. Detta bekräftar inte att det äldre eller nya arbetet körs på YuMi. Den nuvarande [SMC README](https://gitlab.control.lth.se/marko-g/ur_simple_control/-/blob/main/README.md) beskriver UR-stöd, två varianter av mobil YuMi och Heron. UR-grenen använder `ur_rtde`; vissa andra robotar kräver ROS2. Python är belagt av referenskoden; en bestämd ROS-version är inte belagd.

Konkreta begränsningar att hantera vid återanvändning:

- Kameraströmmen är avkommenterad i äldre experiment, men kommenterad i huvudflödet i `robotchess3.py`. Spellopen låter Stockfish välja båda sidors drag; den verifierar inte att ett mänskligt drag faktiskt observerats.
- Brädet antar 45 mm rutor och avgör hörnens schackorientering geometriskt relativt robotens origo. Grip-/höjdoffsetar och fångstposition är hårdkodade. Dessa värden är referenser från en äldre uppställning, inte kalibrering för en ny.
- Ett ogiltigt djup ger `None` från `pixel2coord`, men anroparen packar ändå upp tre värden. Enkameraläget kan dessutom fortsätta till flerpjäslogiken efter sin första `yield`.
- Fångsthanteringen använder destinationsrutan, vilket inte räcker för en passant. Befordran behöver en fysisk pjäsbytesstrategi. Rockadtestets villkor innehåller ett alltid sant stränguttryck.
- Stopp och upprensning i huvudskriptet ligger inte i en generell `finally`; andra fel än tangentbordsavbrott kan hoppa över städningen. Lägg inte en nätverksserver direkt runt skriptets globala robotobjekt.
- Repo-roten saknar beroendemanifest, CI/testsvit och övergripande licensfil i den granskade trädförteckningen. Modellvikter, bilder och träningsdata finns med, men deras återanvändningsvillkor måste bedömas per material. De har inte kopierats in i det nya projektets källkod genom denna granskning.

## RobotLab och kursmaterial

RobotLab ägs gemensamt av reglerteknik och datavetenskap. Den publika inventeringen omfattar bland annat ABB IRB120/140/2400 och YuMi, KUKA IIWA, Franka Panda samt Heron med MiR200 och UR5e. Den visar att flera leverantörsspecifika anslutningar är möjliga, men säger inget om vilken utrustning som är bokad för demonstrationen. [RobotLab: About](https://www.robotics.lth.se/about), [Infrastructure](https://www.robotics.lth.se/infrastructure).

Den aktuella kursplanen för **FRTN85 Tillämpad robotik 2026/27** anger Björn Olofsson som kursansvarig och innehåller robotprogrammering, simulering, kalibrering och ett grupprojekt. Kursprogramvara och övrigt material hänvisas till Canvas. Det offentliga kursprogrammet från 2023 nämner ABB RobotStudio och Peter Corkes MATLAB-toolbox; det är historisk information, inte en verifierad verktygslista för 2026. [Kursplan 2026/27](https://kurser.lth.se/kursplaner/26_27-en/FRTN85.html), [Kursprogram HT2023](https://www.control.lth.se/fileadmin/control/Education/EngineeringProgram/FRTN85FRTN80/FRTN85_FRTN80_Course_Program_HT2023.pdf).

[RobotWiki](https://robotwiki.cs.lth.se/) är labbets dokumentationsingång. [UR5e-sidan](https://robotwiki.cs.lth.se/documentation:robots:ur5e) länkar till SMC och handledningar och beskriver RTDE-alternativet. Dess uppdateringsdatum är 2024-10-30, så praktiska nätuppgifter behöver bekräftas lokalt. Offentlig GitLab-sökning efter FRTN85 och chess gav inga träffar; det är inte belägg för att privata kursrepon saknas.

## Bibliotek och tekniska referenser

| Referens | Belagt innehåll och version/begränsning | Publicerad licens |
| --- | --- | --- |
| [SMC](https://gitlab.control.lth.se/marko-g/ur_simple_control) | Pythonpaket i `python/smc`, simulerad/verklig robot, kontrollslingor och Docker. Nuvarande README stöder fler robotar än ursprungliga UR-inriktningen. | Ingen rotlicens hittades i den granskade rotlistningen; kontrollera paket-/filnivå före distribution. |
| [RobotLab abb_egm_pyclient](https://gitlab.control.lth.se/robotlab/abb_egm_pyclient) | Pythonklient för ABB EGM; README anger test med RobotWare 6.08.01 och generering av protobuf från robotens `egm.proto`. | [MIT](https://gitlab.control.lth.se/robotlab/abb_egm_pyclient/-/blob/main/LICENSE). |
| [RobotLab ABB EGM-instruktioner](https://gitlab.control.lth.se/robotlab/abb_egm_instructions) | EGM-konfiguration, RAPID och RobotStudio-exempel för YuMi. Kräver EGM installerat/licensierat; separat UCDevice per YuMi-arm. | Rotens LICENSE har samma blob som Pythonklientens MIT-licens vid kontrollen. |
| [abb_librws](https://github.com/ros-industrial/abb_librws) | C++ för RWS 1.0: RAPID-data, IO, status och prenumerationer. README anger RobotWare 6.x; 7.x/RWS2 stöds inte. | BSD-3-Clause. |
| [abb_libegm](https://github.com/ros-industrial/abb_libegm) | C++ för EGM över UDP, joint/pose-läge. Kräver enligt README RobotWare minst 6.07.01 och option 689-1. | [BSD-3-Clause](https://github.com/ros-industrial/abb_libegm/blob/master/LICENSE). |
| [SkiROS2](https://github.com/RobotLabLTH/SkiROS2) och [standardbibliotek](https://github.com/RobotLabLTH/skiros2_std_lib) | RobotLab-länkad struktur för robotfärdigheter, beteendeträd och kunskapsmodell. Trots namnet anger README ROS Melodic/Noetic och pågående Humble-port. | LGPL-3.0-or-later enligt respektive LICENSE.md. |
| [Cartesian Impedance Controller](https://github.com/matthias-mayr/Cartesian-Impedance-Controller) | RobotLab-länkad C++-kontroller; ROS2-/ROS1-integration, exempel för Franka och KUKA. Relevant om kraft-/impedansstyrning väljs. | BSD-3-Clause. |

SkiROS och impedanskontrollern finns på [RobotLabs officiella mjukvarusida](https://www.robotics.lth.se/software). Tabellen är ett register över kandidater, inte en rekommendation att installera samtliga. Ett spelkommando kan hållas på applikationsnivå medan robotens rörelse- och stopplogik körs lokalt; det är en teknisk bedömning utifrån den befintliga kodens kontrollgränser.

## WARA-Ops och Ericsson

[WASP:s beskrivning av WARA Ops](https://wasp-sweden.org/research/research-arenas/wara-operational-data/) bekräftar Ericsson Research som driftansvarig, åtkomst till ett levande 5G-nät, molnresurser och övervakningsdata. Portalen erbjuder data och CPU/GPU-miljöer. Detta är generell forskningsinfrastruktur; inga API-endpoints eller tjänstenivåer för den aktuella demonstrationen publiceras där.

En [WASP-uppdatering från 2026-05-08](https://wasp-sweden.org/updates-in-the-wara-ops-portal/) beskriver gemensam Jupytermiljö, kostnadsfri åtkomst för WASP-medlemmar med en kontaktperson som kan intyga åtkomsten, samt planerad CitySim-integration under 2026. Den nämner även samarbete med KINET. CitySim anges som planerat och ska inte räknas som en redan tillgänglig projektkomponent.

[WARA-Ops workshop 2024](https://www.wara-ops.org/Workshop-May2024.html) beskriver Ericsson Garage Lunds 5G-experimentnät och insamling av observationsdata. [Anton Risbergs rapport från 2024](https://wara-ops.org/assets/reports/AntonRisberg-WaraOps-Report.pdf) beskriver historiska radiodata och QoS-analys. Sådana dataset kan inspirera mätfälten, men är inte en prestandamätning av RobotLabs uppställning 2026.

WARA Robotics är en separat arena med bland annat ABB och Ericsson. Dess publika testbäddar och gränssnitt ska inte automatiskt tillskrivas WARA-Ops eller Lundprojektet. [WASP: WARA Robotics](https://wasp-sweden.org/research/research-arenas/wara-robotics/).

## Handspårning i webcam-exemplet

Den första prototypen använde hudfärgssegmentering och kunde därför välja ett ansikte eller huvud. Den är ersatt av [MediaPipe Hand Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python), som använder en förtränad palm-/handmodell och returnerar 21 handlandmärken per upptäckt hand. Repo:t använder pekfingrets fingertopp (landmark 8) och väljer aldrig en punkt från ansiktsdetektion. Modellpaketet laddas lokalt från den officiella MediaPipe-modellservern av `python -m robotlab download-model`.

Som alternativ verifierades [OpenCV:s MediaPipe-handmodell på Hugging Face](https://huggingface.co/opencv/handpose_estimation_mediapipe), som också beskriver 21 hand keypoints och bygger på palm detection. Den används inte som en extra runtime-dependency eftersom MediaPipe Tasks ger en färdig Python-video-loop med tracking och confidence-trösklar. Båda modellspåren är hand-/landmarkdetektion, inte en säkerhetsklassad robotstyrning.

## Uppgifter som återstår inför fysisk integration

- Robotmodell, styrenhet, gripdon, använd SMC-commit och den startkonfiguration som faktiskt fungerade i kursprojektet.
- Nya bräd-/pjäsdimensioner, kalibreringsfiler, tydlig hörnordning, verktygskoordinatsystem och arbetsområde.
- Om den första demon ska vara tre-i-rad, schack eller enbart förflyttning av pjäser; om motspelaren är fjärranvändare, lokal person eller motor.
- Var kommandotjänst, rörelseexekvering och perception ska köras; vilken del av datavägen som verkligen går över 5G.
- Ericssonteamets meddelandekontrakt, åtkomstsätt och ansvar för tidsstämplar, kvittenser, tappad anslutning och återanslutning.
- Aktuella kurs-/labbinstruktioner och villkor för de äldre modellvikterna och träningsbilderna.

Källgranskningen omfattar offentliga labb-, kurs-, WASP-, GitHub- och GitLab-sidor. Canvas och WARA-portalen har inte autentiserats i detta delarbete. Någon offentlig projektspecifikation för just den nya demonstrationen har inte hittats. Alla rekommendationer ovan ska därför läsas tillsammans med projektets mejlbaserade kravunderlag.
