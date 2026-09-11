# Projektbrief: RobotLab/WARA-Ops-demo

## Bekräftat i mejltråden

Källa: ämnet `Projekt i RobotLab?`, skickat av Björn Olofsson 5 september 2026, med svar från Fredrik Sundt samma dag och Markus Lejon samma dag; senaste svar i tråden kom 6 september 2026.

- Arbetet är tänkt att ske i RobotLab under september och oktober 2026.
- WARA-Ops och Ericsson ska ta fram en demo med en robot uppkopplad via 5G.
- Robotdelen ska utvecklas och programmeras av RobotLab.
- Ericssons två timanställda LTH-studenter ska utveckla 5G-/kommunikationsdelen.
- Tre-i-rad nämns som exempel på en fjärrstyrd aktivitet; det är inte ett slutligt spelkrav.
- Projektet liknar Applied Robotics-projektet från föregående år.
- Anställning vid LTH är tänkt, men antal timmar och administration ska planeras senare.
- Björn föreslog ett möte under veckan efter 5 september och skrev att han koordinerar övriga i projektet samt institutionsadministrationen.
- Fredrik uppgav att han är fri tidsmässigt och intresserad. Markus uppgav också att han har möjlighet och stort intresse.

## Inte bekräftat

Robotmodell, gripdon, pjästyp, spelvariant, kameror, positions-/kalibreringsdata, robotdrivrutin, ROS-version, 5G-topologi, API-format, säkerhetsansvar, mätetal, mötestid och budget/timantal saknas i tråden. Det är därför medvetna öppna beslut i [research-dokumentet](research-public.md).

## Beslut i detta repo

Följande lista beskriver den ursprungliga hårdvaruoberoende kärnan. Den har sedan
kompletterats med UR5e/MoveIt/Gazebo-speldemon; se aktuell README och
`implementation-status.md`. Fysisk robot och 5G är fortsatt öppna beslut.

Repo:t implementerar bara sådant som kan testas utan dessa saknade fakta:

1. En ren tre-i-rad-modell med deterministisk optimal motspelare.
2. En geometrisk plan för approach, target och retract i en explicit brädkoordinatram.
3. En simulator som aldrig öppnar en enhet eller skickar rörelsekommandon.
4. Ett lokalt JSON/HTTP-kontrakt med revisionskontroll, deadline, idempotens, kvittens och latched stop/fault.

Det tidigare projektet används bara som läst referens till möjliga framtida integrationsspår. Ingen tidigare källkod eller data är en runtime-dependency här. En fysisk adapter får först läggas till efter att robot, kalibrering och ansvarsfördelning har bekräftats.
