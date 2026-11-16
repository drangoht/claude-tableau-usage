---
name: tableau-usage
description: Met à jour et ouvre le tableau de bord local d'usage de Claude Code (tokens par session, dépôts, dossiers, skills, agents, hooks, outils). À utiliser quand l'utilisateur tape /tableau-usage, ou demande son usage, sa consommation de tokens, quels skills, agents ou hooks ont servi, ou de rafraîchir le tableau de bord.
argument-hint: "[question facultative sur l'usage]"
model: haiku
effort: low
allowed-tools: Bash(python *), Bash(python3 *), Bash(py *)
---

# /tableau-usage — tableau de bord d'usage, sans lire les transcripts

La collecte est faite par un script (aucun token) ; voici sa sortie :

!`PYTHONIOENCODING=utf-8 python3 "${CLAUDE_SKILL_DIR}/scripts/collecte.py" --ouvrir 2>/dev/null || PYTHONIOENCODING=utf-8 python "${CLAUDE_SKILL_DIR}/scripts/collecte.py" --ouvrir 2>&1 || echo "ECHEC de la collecte"`

## Quoi répondre

- Sans question dans `$ARGUMENTS` : recopie les trois lignes ci-dessus (sessions, tokens, chemin de la page) et dis
  que la page est ouverte dans le navigateur. Rien d'autre : pas d'analyse, pas de lecture de fichier.
- Si la sortie contient « ECHEC » ou une erreur Python : relance une fois
  `python "${CLAUDE_SKILL_DIR}/scripts/collecte.py"` avec Bash et rapporte l'erreur telle quelle.
- Avec une question (« quel dépôt a coûté le plus cette semaine ? ») : ne lis jamais les transcripts ni le fichier de
  données en entier. Écris un court script Python qui charge `~/.claude/tableau-usage/donnees-<machine>.json` et
  n'affiche que l'agrégat demandé, puis réponds en une ou deux phrases.

## Format des données (pour les questions)

`donnees-<machine>.json` : `{machine, genere, sessions: [...], journal, hooks_configures}`. Chaque session :
`id, titre, debut, fin, dossier, depot, branche, tok, jm, skills, tok_skills, agents, tok_agents, outils, hooks,
commandes, invites, messages`. Les vecteurs de tokens sont `[entrée, sortie, cache lu, cache écrit]` ; `jm` les
ventile par clé `"AAAA-MM-JJ|modèle"`.

## Autres commandes

- Tout relire en ignorant le cache : `python "${CLAUDE_SKILL_DIR}/scripts/collecte.py" --complet`
- Installer ou retirer le hook de journalisation : `python "${CLAUDE_SKILL_DIR}/scripts/installer.py"` (`--desinstaller`)
- Ajouter un autre poste : copier son `donnees-<machine>.json` dans `~/.claude/tableau-usage/import/`.
