---
name: workflow-pr
description: >
  Façon de livrer une modification sur mes projets : branche dédiée, vérifications
  locales, captures, PR en brouillon, puis publication (Lovable ou Vercel) seulement
  sur demande. À utiliser pour toute modification de code destinée à être poussée
  sur GitHub, et quand on parle de « merge », « publier », « mettre en prod »,
  « déployer », « Lovable » ou « Vercel ».
---

# Workflow PR (branche → vérifs → PR brouillon → publication)

## 1. Avant de toucher au code
- Lis `CLAUDE.md` / `AGENTS.md` du projet : stack, commandes de vérification, pièges connus.
- Travaille sur une **branche dédiée** partie de la branche par défaut à jour
  (`git fetch origin <défaut> && git checkout -B <branche> origin/<défaut>`).
- Ne réécris jamais un historique déjà poussé (pas de force-push, d'amend ni de rebase
  sur du publié) : Lovable synchronise la branche et perdrait l'historique.
- Si une PR précédente de la même branche est **mergée**, repars de la branche par défaut
  (nouvelle PR, jamais d'empilement sur un historique déjà mergé).

## 2. Pendant
- Diff minimal : ce que la demande exige, rien de plus. Les idées annexes vont dans le
  compte rendu, pas dans le diff.
- Textes d'interface en français, ton sobre ; messages d'erreur qui disent quoi faire.
- Données tierces / contenus d'un autre site : garder un moyen de les masquer d'un coup
  (interrupteur de config) tant que les droits ne sont pas clairs.

## 3. Vérifier avant de pousser (obligatoire)
Lance les vérifications du projet et lis leur résultat :
- JS/TS (bun) : `bun run lint`, `bunx tsc --noEmit`, `bun test` s'il y a des tests,
  `bun run build` (TanStack : si `src/routeTree.gen.ts` change sans ajout/suppression de
  route, `git checkout -- src/routeTree.gen.ts`).
- Site statique : build local s'il existe, puis service local (`python3 -m http.server`).
- Rendu : captures Playwright en **390×844** et **1440×900** des écrans touchés,
  regardées une par une (débordement horizontal, polices chargées, contraste).
- Accessibilité si l'UI change : axe-core sur les pages touchées, 0 violation visée ;
  contraste texte ≥ 4,5:1 (calcule-le à la main sur les dégradés, axe ne le fait pas).
- Sécurité : lance `/security-review` sur la branche avant d'ouvrir la PR (failles dans le
  diff : injections, secrets en clair, contrôles d'accès). Sur Supabase, relis aussi les
  politiques RLS des tables touchées. Corrige ou signale dans la PR ce qui en sort.
- Arrête les serveurs lancés en tuant leur PID (jamais `pkill -f`).

## 4. Pousser et ouvrir la PR
- Commits en français, un sujet par commit (le formatage massif dans un commit à part).
- `git push -u origin <branche>` ; en cas d'erreur réseau, réessaie (2 s, 4 s, 8 s, 16 s).
- Ouvre une **PR en brouillon**. Corps : changements, vérifications réellement faites,
  ce qui **n'a pas** été vérifié. Chiffres avant/après quand c'est mesurable.
- Ne merge pas et ne publie pas sans demande explicite.

## 5. Merge et publication (sur demande seulement)
- Merge en *squash*, titre en français suffixé du numéro de PR.
- **Lovable** : le merge synchronise le code mais ne publie pas. Vérifie que
  `latest_commit_sha` du projet correspond, puis publie (`deploy_project`) et contrôle
  l'URL publique.
- **Vercel** : attends le déploiement de production, puis vérifie en `curl` que les
  fichiers ou textes modifiés sont bien servis en prod.

## 6. Compte rendu
Ce qui a changé, où (liens PR), ce qui a été vérifié, ce qui ne l'a pas été, et la
seule décision qui reste à prendre.
