# Implementationsstatus – 11 september 2026

Den nya skrivbordsstartaren kör ett helt tre-i-rad-spel i simulering med
kamerabekräftelse efter varje placering. Två fullständiga omgångar efter
rättningarna passerade: **18 av 18 placeringar**, två i varje ruta.

## De fem stegen

| Steg | Implementerat | Återstår |
| --- | --- | --- |
| 1. Riktig pekstyrning | Separat pekningstest; verklig webcam och MediaPipe startade; full UI med simulatorkamera provad utan att skicka robotkommandon; handbortfall/byte av mål testade automatiskt | En person behöver genomföra ett helt spel med faktisk pekning enligt manualen |
| 2. Tydlig återkoppling | Svenska steg- och felmeddelanden, röda/blå symboler, vinst/oavgjort, Nytt spel, avslutning och loggåtkomst | Praktisk användaråterkoppling |
| 3. Helt spel | Fem röda och fyra blå pjäser, optimal motspelare, turordning, upptagna rutor, kameraverifierad spelställning, full scenåterställning | Fysisk utformning av pjäsmatning |
| 4. Tillförlitlighet | Upprepningsbara spel-/cell-/felprov, försöksspårning och mätning per ruta, strikt avvisning av gamla/dubbla kommandon, kamera- och gripfel | Fler prov under andra ljus-/lastförhållanden; fysisk validering |
| 5. Robot och 5G | Befintliga gränser separerade; det lokala API:et dokumenterat; offentliga WARA-Ops-/Ericsson-källor granskade | Robot, gripdon, kalibrering, labbansvar och verkligt kommunikationskontrakt är fortfarande öppna |

Pjäslagret är en **simulerad dispenser**: varje ny pjäs skapas en gång vid en
gemensam hämtplats. Redan placerade pjäser ligger kvar i fysik- och
kollisionsmodellerna. Vi har inte valt eller modellerat ett fysiskt magasin.

## Validering

- 96 Python-tester passerade lokalt, inklusive kamerafall för båda färgerna
  i alla nio rutor, avbrott, felaktiga kvittenser och transportregressioner.
- Två hela Windows → lokal HTTP → WSL → MoveIt → UR5e → gripdon → renderad
  kamera-spel passerade och slutade oavgjort. Inmatningen var syntetisk.
- Samtliga 18 placeringar hade tre färska bekräftande kamerabilder. Varje ruta
  användes två gånger. Medianen för en placering var cirka 36 sekunder och
  95:e percentilen cirka 48 sekunder i dessa två körningar.
- HTTP-proven avvisade gamla sessioner, dubbletter och gamla observationer;
  uppehåll i bildflödet och byte av mål krävde ny stabilitetsbekräftelse.
- Två separata felprov passerade: injicerat kamerabortfall och uteblivet grepp
  när sugfunktionen hölls avstängd. Båda låste försöket, behöll tomt spelbräde
  och avvisade nya pekningar efter att handen släppts.
- Gripdonets fysikprov verifierade avvisad distansinfästning, kontakt, bärning,
  släpp och avvisat byte av vald pjäs medan gripdonet redan höll en pjäs.
- Webbkamerans svenska testfönster samt kombinationen webcam/simulatorkamera
  startade och avslutades. Robot-POST blockerades under dessa UI-prov.

Exakta körnings-id, kameraevidens och felprovsresultat finns i
[validation-2026-09-11.json](validation-2026-09-11.json). Fullständiga lokala
loggar ligger i `artifacts/`; de ingår inte i Git. Rapporten avser de angivna
testkörningarna, inte en garanti för alla kommande användningsfall.

Tidigare utvecklingskörningar hittade två fel som rättades före de två slutliga
spelproven: för snäv väntan på rörelser under långsam simulering, samt antagandet
att `ign topic -n 1` alltid ger exakt ett JSON-meddelande. Simulatorklockan är
nu gemensam för MoveIt och robot-state-publisher, ROS-resurser frigörs efter
varje placering, rörelseväntan har en avgränsad simuleringsmarginal och
statusläsaren hanterar kompletta meddelandeserier utan att ignorera trasig data.

## Kör själv

Dubbelklicka på **RobotLab** på skrivbordet eller **Starta RobotLab.cmd**.
Välj **Testa pekning utan robotrörelse** för att börja med handdetektionen.
**Nytt spel** startar sedan den fulla simuleringen.

För upprepning av systemproven, stäng först skrivbordsprogrammet:

```text
python -m unittest discover -s tests
python -m robotlab.acceptance --game --repeats 2
python -m robotlab.acceptance --cells --repeats 3
python -m robotlab.acceptance --faults
```

Se [manuellt acceptansprov](manual-acceptance.md),
[pekningsprotokoll](live-protocol.md) och
[öppna integrationsbeslut med källor](integration-open.md).

Den installerade Humble-versionen av MoveIt kan fortfarande rapportera ett
känt fel vid processavslutning. Startaren avslutar sin egen processgrupp;
detta har inte inneburit ett godkänt felaktigt drag. Fysisk robot, fysisk
kamerakalibrering och faktisk 5G-trafik har inte testats eller kopplats in.
