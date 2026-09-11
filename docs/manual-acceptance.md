# Praktiskt prov med en person

Status: inte genomfört av agenten. Automatiska syntetiska tester ersätter inte detta prov.

1. Dubbelklicka på RobotLab. Välj **Testa pekning utan robotrörelse**.
   Peka i var och en av de nio rutorna. Kontrollera att rätt rutnummer visas.
2. Håll kvar kortare än cirka 1,2 sekunder, byt ruta och ta bort handen.
   Bekräftelsen ska nollställas. Testa även otydlig hand och ändrad belysning.
3. Välj **Nytt spel**. Peka på en tom ruta tills draget accepteras. Kontrollera
   att röd pjäs placeras i rätt ruta, att kameran bekräftar den och att roboten
   därefter placerar sin blå pjäs.
4. Håll kvar handen medan roboten arbetar. Det får inte skapa ett extra drag.
   Ta bort handen och välj nästa tomma ruta. Fortsätt tills vinst eller oavgjort.
5. Prova att välja en upptagen ruta. Prova **Nytt spel** samt att stänga fönstret.
   Nytt spel ska ge ett tomt bräde; stängning ska avsluta den egna simulatorn.

Anteckna datum, testperson, vilka rutor som fungerade, ljusförhållanden och eventuella fel.
Spara vilket `live-<sessions-id>.jsonl` som hör till försöket. Det innehåller
kommandots klientrapporterade källa och kamerabekräftade drag, inga handkamerabilder.
Klientens källmarkering är inte en oberoende identitetskontroll; manuellt godkännande
ska ange att en person faktiskt utförde provet.

| Prov | Resultat | Logg / kommentar |
| --- | --- | --- |
| Alla nio pekrutor | Ej utfört | |
| Hand bort / ändrad ruta / svag detektion | Ej utfört | |
| Ett helt spel med verklig pekning | Ej utfört | |
| Kvarhållen hand och upptagen ruta | Ej utfört | |
| Nytt spel och avstängning | Ej utfört | |
