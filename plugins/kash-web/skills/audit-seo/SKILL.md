---
name: audit-seo
description: Lance un audit Google Lighthouse (Performance, Accessibility, Best Practices, SEO) sur une URL locale ou distante et résume les résultats. Utiliser quand l'utilisateur demande un audit SEO/perf, un score Lighthouse, ou invoque /audit-seo [URL].
argument-hint: "[URL]"
---

# Audit SEO & Performance (Lighthouse)

## Prérequis d'environnement
Pas de binaire `lighthouse` global installé — utiliser `npx lighthouse` (le package est
résolu à la volée depuis npm, pas d'installation préalable requise).
Aucun Chrome système dans le PATH : pointer `CHROME_PATH` vers le Chromium de Playwright
déjà présent sur la machine. Le process tournant en root dans un conteneur, `--no-sandbox`
est obligatoire (Chrome refuse de démarrer sinon).

## Étapes

1. Déterminer l'URL à tester : celle fournie par l'utilisateur, sinon `http://localhost:3000`.
   Si rien ne répond sur ce port, demander l'URL ou le port réel plutôt que de deviner.

2. Générer le rapport JSON dans un fichier temporaire :
   ```bash
   CHROME_PATH=/opt/pw-browsers/chromium-1194/chrome-linux/chrome npx --yes lighthouse "<URL>" \
     --output=json --output-path=/tmp/lighthouse-report.json \
     --chrome-flags="--headless --no-sandbox --disable-gpu" \
     --only-categories=performance,accessibility,best-practices,seo
   ```
   (Si le chemin `chromium-1194` n'existe plus — version bumpée — lister
   `/opt/pw-browsers/` et ajuster.)

3. Lire `/tmp/lighthouse-report.json` et extraire les 4 scores :
   ```bash
   python3 -c "
   import json
   d = json.load(open('/tmp/lighthouse-report.json'))
   for k in ['performance','accessibility','best-practices','seo']:
       print(k, round(d['categories'][k]['score']*100))
   "
   ```

4. Présenter un tableau propre :

   | Catégorie | Score |
   |---|---|
   | Performance | X/100 |
   | Accessibility | X/100 |
   | Best Practices | X/100 |
   | SEO | X/100 |

5. Identifier les 3 recommandations les plus prioritaires : dans `d['audits']`, filtrer les
   entrées avec `score is not None and score < 1`, trier par `details.overallSavingsMs` ou
   par poids dans `d['categories']['performance']['auditRefs']` (champ `weight`) quand
   disponible, sinon par ordre d'apparition. Pour chacune, donner le titre de l'audit et,
   en une phrase, le fichier/section du code concerné (croiser avec la structure du projet,
   ne pas se contenter de recopier la description générique de Lighthouse).

6. Supprimer `/tmp/lighthouse-report.json` une fois l'analyse terminée.

## Notes
- Chaque commande Bash exécutée est visible dans la conversation comme n'importe quel autre
  outil — rien ne tourne en tâche de fond ni caché à l'utilisateur.
- Un score Performance dépend fortement de la machine qui l'exécute (ce conteneur n'a pas le
  même CPU/réseau qu'un vrai appareil) : le présenter comme indicatif, pas absolu.
