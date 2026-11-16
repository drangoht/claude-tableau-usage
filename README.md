# claude-tableau-usage

Tableau de bord local de votre usage de [Claude Code](https://claude.com/claude-code) : tokens par session, par jour
et par modèle, dépôts git et dossiers concernés, skills, sous-agents, hooks, outils et commandes « / » utilisés.

Tout est calculé sur votre poste par un script Python, **sans aucun appel au modèle** : mettre le tableau à jour ne
consomme pas de tokens. La page produite est un seul fichier HTML autonome, lisible hors ligne, en thème clair ou
sombre selon le système.

## Ce que contient le dépôt

| Fichier | Rôle |
|---|---|
| `scripts/collecte.py` | Lit les transcripts de `~/.claude/projects`, agrège, écrit la page et l'export JSON |
| `scripts/journal.py` | Hook de journalisation : note chaque skill, sous-agent, commande et session, puis relance la collecte |
| `scripts/installer.py` | Pose (ou retire) les hooks dans `~/.claude/settings.json` |
| `scripts/gabarit.html` | Gabarit de la page (graphiques en SVG, aucun fichier externe) |
| `SKILL.md` | Skill `/tableau-usage`, réglé sur le modèle Haiku |

## Prérequis

- Claude Code récent (les hooks utilisent la forme `command` + `args` et l'option `async`).
- Python 3.8 ou plus, bibliothèque standard seule.
- Sous Windows, Git Bash pour la commande `/tableau-usage` (il est installé avec Git pour Windows).

## Installation

Le dossier se clone directement à l'emplacement des skills personnels, ce qui rend la commande `/tableau-usage`
disponible dans toutes les sessions :

```bash
git clone https://github.com/drangoht/claude-tableau-usage "$HOME/.claude/skills/tableau-usage"
```

Puis l'installeur pose les hooks et génère le tableau une première fois :

```bash
python "$HOME/.claude/skills/tableau-usage/scripts/installer.py"
```

Sous macOS et Linux, remplacez `python` par `python3`. L'installeur :

- garde une copie de vos réglages dans `~/.claude/settings.json.avant-tableau-usage` (à la première installation) ;
- ajoute ses hooks sans toucher aux vôtres, et peut être relancé sans créer de doublons ;
- inscrit le chemin absolu de l'interpréteur Python qui l'a lancé : relancez-le si vous changez de Python.

Les hooks sont pris en compte par les sessions ouvertes après l'installation.

## Utilisation

- **Automatique** : le tableau est régénéré à la fin de chaque session, et au plus toutes les 10 minutes pendant le
  travail. Ouvrez `~/.claude/tableau-usage/tableau.html` dans un navigateur.
- **À la demande** : tapez `/tableau-usage` dans Claude Code. Le script s'exécute avant que le modèle ne lise le
  skill ; Haiku ne fait que recopier trois lignes de résumé et la page s'ouvre dans le navigateur.
- **Sans Claude** :

```bash
python "$HOME/.claude/skills/tableau-usage/scripts/collecte.py" --ouvrir
```

Options de `collecte.py` : `--ouvrir` (ouvre la page), `--complet` (ignore le cache et relit tout),
`--silencieux` (aucune sortie).

Dans la page : filtre de période (7, 30, 90 jours, tout), bascule « avec ou sans lecture de cache », survol des
graphiques pour le détail, clic sur une barre pour filtrer la table des sessions, tri par colonne.

## Plusieurs postes

Chaque collecte écrit `~/.claude/tableau-usage/donnees-<machine>.json`. Pour voir un autre poste dans le même tableau,
copiez son fichier dans `~/.claude/tableau-usage/import/` du poste où vous consultez la page, puis relancez la
collecte. Un sélecteur de poste apparaît dès qu'il y en a plusieurs.

## D'où viennent les chiffres

| Donnée | Source |
|---|---|
| Tokens (entrée, sortie, cache lu, cache écrit) | champ `usage` des réponses dans les transcripts, dédoublonné par message |
| Dossier, branche | champs `cwd` et `gitBranch` des transcripts |
| Dépôt | dossier `.git` trouvé en remontant depuis le dossier de travail ; `owner/depot` si un remote `origin` existe |
| Skills | appels de l'outil `Skill`, et tokens marqués `attributionSkill` |
| Agents | appels de l'outil `Agent`, et tokens des transcripts de sous-agents |
| Hooks | traces de hooks dans les transcripts, hooks déclarés dans `settings.json`, journal du hook |
| Commandes | balises `<command-name>` des messages utilisateur |

Le cache (`cache.json`) conserve le résumé de chaque session : l'historique reste dans le tableau après la purge des
transcripts par Claude Code (`cleanupPeriodDays`).

## Limites

- Les tokens sont ceux déclarés par l'API dans les transcripts ; aucun coût en euros ou en dollars n'est estimé.
- Les compteurs de skills, agents, outils et hooks portent sur les sessions actives pendant la période choisie, pas
  sur chaque jour.
- Le dépôt n'est retrouvé que si le dossier de travail existe encore au moment de la première collecte.
- Les hooks déclenchés avant l'installation ne sont connus que par les traces qu'ils ont laissées dans les transcripts.

## Confidentialité

Rien ne quitte le poste. Les données restent dans `~/.claude/tableau-usage/`, hors de ce dépôt. La page contient les
titres de vos sessions, vos chemins de dossiers et vos noms de dépôts : ne la partagez qu'en connaissance de cause.
Les identifiants éventuellement présents dans l'URL d'un remote git sont retirés.

## Désinstallation

```bash
python "$HOME/.claude/skills/tableau-usage/scripts/installer.py" --desinstaller
```

Supprimez ensuite `~/.claude/skills/tableau-usage` (le skill) et, si vous ne voulez plus des données,
`~/.claude/tableau-usage`.
