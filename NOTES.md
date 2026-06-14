\# NOTES.md — Audit du code legacy QUANTA



\## compute.py



\### Ce qui fonctionne

\- \[fonction X] : fait quoi, semble correct

\- ...



\### Ce qui est cassé / fragile

\- \[fonction Y] : pourquoi ça casse, dans quel cas

\- ...



\### À garder pour v2

\- ...



\### À jeter

\- ...



\## brain.py — Logique des 8 phases



1\. Phase 1 : \[description courte] — input / output

2\. Phase 2 : ...

... (jusqu'à 8)



\### Constat

\- Combien de phases sont vraiment nécessaires dans la v2 (cf. Jour 16 : 1 seul appel LLM) ?

\- Quelle logique de chaque phase peut être récupérée et codée en dur (sans LLM) ?

