---
name: veille-awwwards
description: Before designing or redesigning a website, a landing page or a key screen, look at what the best sites on Awwwards do (Sites of the Day, categories close to the project), pick 3–5 relevant references, visit them for real, and turn what works into a design direction adapted to the project's audience, accessibility and performance. Use with frontend-design (creating) and impeccable (critique). Triggers - "nouveau site", "refonte", "landing", "hero", "page d'accueil", "rendre le site plus marquant", "direction visuelle", "inspiration".
---

# Veille Awwwards

Awwwards n'est qu'un **annuaire** : le site lui-même n'a rien d'exceptionnel. Ce sont
les sites qu'il récompense qui montrent ce qui se fait de mieux en interface :
typographie, mise en page, mouvement, récit. On passe donc peu de temps sur Awwwards
(trouver les adresses) et l'essentiel sur les sites eux-mêmes. Les regarder **avant** de concevoir
donne une vraie valeur supplémentaire à l'expérience. Mais un site primé n'est pas
un modèle de qualité tel quel : beaucoup sacrifient accessibilité, lisibilité et
performance au spectacle. On s'en inspire, on ne recopie pas.

## Quand

- Nouveau site, refonte, page d'accueil, landing, hero, écran clé.
- Avant `frontend-design` (pour nourrir la direction visuelle) ; `impeccable` vient
  après, pour critiquer ce qu'on a fait.
- Pas pour une correction ponctuelle (un bouton, un bug d'affichage).

## Étapes

### 1. Cadrer (2 minutes)
Noter : le type de projet (institution, patrimoine, e-commerce, outil métier, jeu…),
le public (expert ou non, âge, mobile ou ordinateur), le ton voulu, les contraintes
(stack, hébergement, budget de performance, pas de WebGL si la machine cible est
modeste…). Ces critères servent à choisir les références, pas seulement le « joli ».

### 2. Chercher sur Awwwards
`curl` est souvent bloqué par Awwwards (protection anti-robots) : utiliser **WebFetch**.
- Sites du jour récents : `https://www.awwwards.com/websites/sites_of_the_day/`
- Par catégorie : `https://www.awwwards.com/websites/<categorie>/`
  (ex. `architecture`, `culture-education`, `e-commerce`, `institutions`,
  `design-agencies`, `fashion`, `games-entertainment`, `photography`…)
- Par technologie : `https://www.awwwards.com/websites/<techno>/` (gsap, webgl, three-js…)
- Recherche web ciblée : `site:awwwards.com <thème du projet>` (WebSearch).

Retenir **3 à 5 références proches du projet par leur usage** (même type de contenu,
même public), plus éventuellement une plus audacieuse pour élargir.

### 3. Récupérer l'adresse du site (rapide)
WebFetch sur `https://www.awwwards.com/sites/<slug>` pour l'URL du vrai site ; au
passage, technologies et note d'**ergonomie** (basse = à admirer de loin). Ne pas
s'attarder : la fiche ne remplace pas la visite.

### 4. Visiter le vrai site — l'étape qui compte
Parcourir le site comme un visiteur, avec Playwright (voir `webapp-testing`) :
- accueil, puis 2 ou 3 pages intérieures, en **1440 px et 390 px** ;
- défiler la page par étapes (captures successives) : beaucoup d'effets naissent au
  défilement ; attendre quelques secondes pour les animations d'entrée ;
- survoler et cliquer les éléments clés (menu, cartes, boutons) pour voir les
  micro-interactions et les transitions de page ;
- noter ce qui marque, *et pourquoi* (le détail qui fait l'effet).
Observer aussi : au clavier (Tab), avec `prefers-reduced-motion`, poids et lenteur.

Environnement cloud Claude Code : si Chromium refuse le certificat
(`ERR_CERT_AUTHORITY_INVALID`), c'est le proxy de l'environnement. Ne pas désactiver
la vérification TLS ; ajouter seulement les clés des autorités du proxy :
`--ignore-certificate-errors-spki-list=<empreintes SPKI des certificats « Anthropic »
de /root/.ccr/ca-bundle.crt>` (calcul : `openssl x509 -pubkey -noout | openssl pkey
-pubin -outform der | openssl dgst -sha256 -binary | base64`).

### 5. Extraire ce qui se transpose
Pour chaque référence, noter en une ligne par rubrique :
- **Typographie** : familles, contraste de tailles, graisse, casse.
- **Mise en page** : grille, rythme, blancs, ruptures.
- **Mouvement** : entrées, transitions de page, défilement, micro-interactions.
- **Récit** : comment le contenu se découvre (ordre, chapitres, carte, temps).
- **Couleur et matière** : palette, photo/illustration, texture.
Puis trier : *à reprendre* (sert le propos et le public) / *à éviter* (spectacle qui
gêne la lecture, l'accès ou la vitesse).

### 6. Adapter avec des garde-fous
- Contraste WCAG AA, navigation au clavier, focus visible, textes réels (pas d'images
  de texte), `prefers-reduced-motion` respecté (animations coupées ou réduites).
- Le contenu reste lisible sans JavaScript lourd ; WebGL et vidéo en amélioration
  progressive, jamais indispensables pour lire ou naviguer.
- Mobile d'abord pour les publics non experts ; budget de poids et de chargement tenu.
- Ne jamais copier le code, les textes, les images ou les polices sous licence d'un
  site : on reprend des **principes**.

### 7. Livrer
Une courte **planche de références** (dans la PR ou `docs/references-design.md`) :
pour chaque site, lien Awwwards + lien du site, ce qu'on reprend, ce qu'on écarte.
Puis concevoir avec `frontend-design`, et critiquer le résultat avec `impeccable`.
