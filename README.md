# kash-plugins

Mes lots de skills Claude Code, un plugin par type de tâche. Un seul endroit à
tenir à jour : chaque projet, sur le Mac comme dans le cloud, charge les lots
dont il a besoin depuis ce dépôt.

## Les lots

| Lot | Pour quoi | Skills |
|---|---|---|
| `kash-founder` | Piloter un projet comme un fondateur : plan, offre, prix, marque, lancement, concurrents, finances, conseil. | founder-board, founder-brand, founder-cfo, founder-competitors, founder-consumer, founder-launch, founder-marketing, founder-offer, founder-ops, founder-plan, founder-pricing |
| `kash-instagram` | Instagram : plan éditorial, Reels, carrousels, stories, légendes, réponses et DM, audit de compte, sans ton IA. | ig-audit, ig-caption, ig-carousel, ig-comment, ig-dm, ig-human, ig-plan, ig-profile, ig-reel, ig-reply, ig-repurpose, ig-story, ig-viral |
| `kash-marketing` | Marketing : stratégie de contenus et tarifs. | content-strategy, pricing |
| `kash-media` | Visuels : affiches PNG/PDF, schémas soignés, résumé de vidéos YouTube. | canvas-design, diagram-design, video-lens |
| `kash-python` | Python : patterns, tests, sécurité des agents de trading LLM. | llm-trading-agent-security, python-patterns, python-testing |
| `kash-supabase` | Supabase : bonnes pratiques Postgres, RLS, auth et stockage. | supabase, supabase-postgres-best-practices |
| `kash-web` | Sites web : audits SEO (Lighthouse, technique, IA), règles d'interface, tests d'app web, navigateur piloté, veille Awwwards, aspiration de vieux sites. | agent-browser, ai-seo, audit-seo, legacy-site-crawler, scrapling, seo-audit, veille-awwwards, web-design-guidelines, webapp-testing |
| `kash-workflow` | Façon de travailler : livrer par PR (workflow-pr), se faire cuisiner sur un plan, débogage méthodique, vérifier avant de dire « fini », mémoire de projet, réponses courtes. | agent-memory, caveman, find-skills, grill-me, grilling, i-have-adhd, search-first, skill-creator, systematic-debugging, verification-before-completion, workflow-pr |
| `impeccable` | Design d'interface : critique, audit, polish | dépôt de l'auteur ([pbakaus/impeccable](https://github.com/pbakaus/impeccable)) |
| `ponytail` | Le moins de code possible | dépôt de l'auteur ([DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail)) |
| `ux-ui-agent-skills` | Kit design system (tokens, composants, accessibilité) | dépôt de l'auteur ([plugin87/ux-ui-agent-skills](https://github.com/plugin87/ux-ui-agent-skills)) |
| `frontend-design` | Interfaces avec une vraie direction visuelle | dépôt officiel d'Anthropic |

Les quatre derniers ne sont pas copiés ici : le catalogue pointe vers le dépôt de
leur auteur, ils se mettent donc à jour avec lui.

## Utilisation

**Sur le Mac** (une fois) : le dossier `~/Desktop/Claude/marketplace` est un clone
de ce dépôt.
```
/plugin marketplace add ~/Desktop/Claude/marketplace
/plugin install kash-workflow@kash-plugins
```
Ajouté par son chemin local, le catalogue est lu directement : un skill modifié
est pris en compte à la session suivante. `git push` pour le publier ailleurs.

**Dans un projet** (Mac et cloud) : copier le bloc du type de projet dans
`.claude/settings.json` à la racine du projet. Claude Code propose alors les lots
à chaque session, y compris dans les sessions cloud lancées depuis le téléphone.

### Site web
(+ `kash-supabase` si base de données, `kash-marketing` pour un client)
```json
{
  "extraKnownMarketplaces": {
    "kash-plugins": {
      "source": {
        "source": "github",
        "repo": "JB198203/claude-marketplace"
      }
    }
  },
  "enabledPlugins": {
    "kash-workflow@kash-plugins": true,
    "kash-web@kash-plugins": true,
    "impeccable@kash-plugins": true,
    "frontend-design@kash-plugins": true,
    "ponytail@kash-plugins": true
  }
}
```

### Jeu
```json
{
  "extraKnownMarketplaces": {
    "kash-plugins": {
      "source": {
        "source": "github",
        "repo": "JB198203/claude-marketplace"
      }
    }
  },
  "enabledPlugins": {
    "kash-workflow@kash-plugins": true,
    "frontend-design@kash-plugins": true,
    "ponytail@kash-plugins": true,
    "kash-media@kash-plugins": true
  }
}
```

### Programme Python (EasyRAG, Trady…)
```json
{
  "extraKnownMarketplaces": {
    "kash-plugins": {
      "source": {
        "source": "github",
        "repo": "JB198203/claude-marketplace"
      }
    }
  },
  "enabledPlugins": {
    "kash-workflow@kash-plugins": true,
    "kash-python@kash-plugins": true,
    "ponytail@kash-plugins": true
  }
}
```

### Musique KASHING / promo
```json
{
  "extraKnownMarketplaces": {
    "kash-plugins": {
      "source": {
        "source": "github",
        "repo": "JB198203/claude-marketplace"
      }
    }
  },
  "enabledPlugins": {
    "kash-workflow@kash-plugins": true,
    "kash-media@kash-plugins": true,
    "kash-instagram@kash-plugins": true,
    "kash-marketing@kash-plugins": true
  }
}
```

## Modifier ou ajouter un skill
1. Mettre le dossier du skill dans `plugins/<lot>/skills/<nom>/` (avec son `SKILL.md`).
2. Skill d'un autre auteur : garder son fichier de licence et l'ajouter à `THIRD_PARTY.md`.
3. Vérifier : `claude plugin validate .`
4. `git push`. Pas de numéro de version : chaque commit est une nouvelle version.

## Notes
- `kash-instagram` lit ta voix dans `~/.claude/instagram/voice.md` : partir de
  `plugins/kash-instagram/voice-modele.md`. Ce fichier est propre à chaque machine.
- `agent-memory` écrit ses notes dans `.claude/memories/` du projet. Jamais de secret dedans.
- `ponytail` (version officielle) tient un petit journal du coût de chaque tâche ;
  ses 4 réglages sont facultatifs (`/plugin configure ponytail@kash-plugins`).
- `agent-browser`, `video-lens` et `find-skills` demandent un outil à installer (voir leur `SKILL.md`).
