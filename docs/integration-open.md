# Fysisk robot och 5G – öppna beslut

Kontrollerat 2026-09-10. Användaren har bekräftat att roboten ännu inte är vald.
UR5e och sugkoppen är därför fortsatt referenser i simuleringen.

## Vad offentliga källor faktiskt dokumenterar

- [WASP: WARA Ops](https://wasp-sweden.org/research/research-arenas/wara-operational-data/)
  beskriver Ericsson Research som ansvarig och tillgång till ett levande 5G-nät,
  molnresurser och övervakningsdata.
- [WARA-Ops](https://www.wara-ops.org/) beskriver forskningsinfrastruktur,
  data-/modellportal och projekt med 5G-åtkomst. Portalen är inte ett publicerat
  robotstyrnings-API.
- [Workshop vid Ericsson Lund](https://www.wara-ops.org/Workshop-May2024.html)
  beskriver experimentmiljön och forskningsbakgrunden.
- [Ericsson: Network and service exposure](https://www.ericsson.com/en/core-network/network-exposure)
  beskriver hur nätverksfunktioner exponeras via API:er. Det fastställer inte
  att vår demo har åtkomst till något visst API, någon viss QoS-tjänst eller endpoint.

I dessa granskade källor hittades inget kontrakt med adresser, autentisering,
robotmodell eller garanti för just vår demo. Vi lämnar detta öppet. WARA Robotics
och WARA-PS är inte belägg för vilka komponenter WARA-Ops-projektet har tillgång till.

## Gränser som redan finns i programmet

Det implementerade meddelandeformatet och kvittensflödet beskrivs i
[det lokala pekningsprotokollet](live-protocol.md).

- Kameran levererar tidsstämplad intention. Sessions-id, stigande sekvensnummer,
  högst 500 ms gamla observationer och stabil pekning kontrolleras lokalt.
- Spelkärnan väljer en ruta och tillåter bara lagliga turer. Robotplanering,
  gripdon och kamerabekräftelse ligger separat från spelreglerna.
- MoveIt-adaptern och Gazebo-kameran är de enda integrerade exekveringsvägarna
  i den nya speldemon. Ett kamerakvitto från simuleringen får inte presenteras
  som fysisk validering. `VerifiedMatch` accepterar för närvarande uttryckligen
  endast denna verifierade simulatorkälla.
- Windows/WSL-bryggan lyssnar bara på loopback. Dess protokoll är vårt förslag,
  inte Ericssons protokoll. Kamerabilder från handen skickas inte vidare.

## Beslut inför implementation av riktig adapter

| Behövs | Status | Varför |
| --- | --- | --- |
| Robot, styrenhet och godkänd drivrutin/version | Öppet | Bestämmer rörelse- och stoppgränssnitt |
| Gripdon, verktygsgeometri, gripkvittens, pjäsmatning | Öppet | Den simulerade dispensern har ingen fysisk motsvarighet ännu |
| Robotbas, bord, kamera och uppmätt kalibreringsfel | Öppet | Simuleringskoordinater får inte återanvändas som labbmätning |
| Arbetsområde, hastigheter, lokal stoppfunktion och ansvarig | Öppet | Krävs för att genomföra fysiska rörelseprov |
| Godkänd nätväg, tjänsteadresser, åtkomst och autentisering | Öppet | Ska komma från labbet/Ericsson; inga adresser gissas |
| Vilken trafik går över 5G och vilka API:er behövs? | Öppet | IP-transport av spelkommandon och styrning av nätets QoS är olika gränssnitt |
| Tidsbas, fördröjningsbudget, kvittenser och återanslutning | Öppet | Gamla eller osäkra kommandon ska inte spelas om |

Ordning när uppgifterna finns: läs robotstatus utan rörelse; verifiera kalibrering
och lokal stoppfunktion; kör lokal rörelse utan pjäs; kör lokal kameraövervakad
placering; lägg därefter till den bekräftade 5G-vägen och mät fördröjningar/avbrott.
Fysisk styrning och faktisk 5G-integration är inte implementerade eller verifierade.
