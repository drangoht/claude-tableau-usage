#!/usr/bin/env python3
"""Génère une page de démonstration avec des données fictives (aucune donnée réelle n'est lue).

  python demo.py [chemin de sortie]     par défaut : demo.html à côté du README

Sert aux captures d'écran du README et à essayer la page avant d'installer quoi que ce soit.
"""
import datetime
import json
import os
import random
import sys

import collecte

ICI = os.path.dirname(os.path.abspath(__file__))
PROJETS = [  # dossier, dépôt, branche, poids
    ("C:\\Travail\\boutique-web", "acme/boutique-web", "main", 5),
    ("C:\\Travail\\api-facturation", "acme/api-facturation", "feature/export-pdf", 4),
    ("C:\\Travail\\outils-internes", "acme/outils-internes", "main", 2),
    ("C:\\Perso\\blog", "moi/blog", "main", 2),
    ("C:\\Perso\\jeu-de-plateau", "moi/jeu-de-plateau", "prototype", 3),
    ("C:\\Notes", None, None, 1),
]
TITRES = ["Corriger le calcul de TVA", "Refonte du panier", "Export PDF des factures", "Migration vers .NET 11",
          "Tests de charge de l'API", "Page d'accueil du blog", "Règles du jeu : phase de pioche", "Script de sauvegarde",
          "Revue de la pull request", "Mise à jour des dépendances", "Tableau de bord des ventes", "Nettoyage du CSS",
          "Import des clients depuis CSV", "Documentation de l'API", "Bug d'arrondi sur les remises", "Résumé de réunion"]
MODELES = [("claude-opus-5-5", 6), ("claude-fable-5-2", 2), ("claude-sonnet-5-5", 2), ("claude-haiku-5-5", 1)]
SKILLS = ["code-review", "dataviz", "anthropic-skills:pdf", "relais", "tableau-usage", "anthropic-skills:xlsx", "deploiement"]
AGENTS = ["Explore", "general-purpose", "web-fetch", "Plan"]
OUTILS = [("Bash", 40), ("Read", 30), ("Edit", 28), ("Write", 12), ("Grep", 10), ("Glob", 4), ("Agent", 2), ("Skill", 1),
          ("WebSearch", 2), ("mcp__github__create_pull_request", 1)]


def choisir(alea, pondere):
    return alea.choices([x[0] for x in pondere], weights=[x[-1] for x in pondere])[0]


def sessions(alea, machine, nombre, jours):
    aujourdhui, sortie = datetime.datetime.now().replace(hour=9, minute=0, second=0, microsecond=0), []
    for n in range(nombre):
        dossier, depot, branche, _ = alea.choices(PROJETS, weights=[p[3] for p in PROJETS])[0]
        debut = aujourdhui - datetime.timedelta(days=int(alea.triangular(0, jours, 0)), minutes=-alea.randrange(600))
        modele, taille = choisir(alea, MODELES), alea.lognormvariate(0, 0.9)
        jm, tok_skills, tok_agents, skills, agents = {}, {}, {}, {}, {}
        sortie_tok = int(60000 * taille)
        principal = [int(400 * taille), sortie_tok, int(sortie_tok * alea.uniform(40, 220)), int(sortie_tok * alea.uniform(2, 6)), 0]
        principal[4] = int(principal[3] * 0.9)
        jm[debut.strftime("%Y-%m-%d") + "|" + modele] = principal
        for s in alea.sample(SKILLS, alea.choice([0, 0, 1, 1, 2])):
            skills[s] = alea.randint(1, 3)
            tok_skills[s + "|" + modele] = [int(x * alea.uniform(0.03, 0.15)) for x in principal]
        for a in alea.sample(AGENTS, alea.choice([0, 0, 0, 1, 2])):
            agents[a] = alea.randint(1, 4)
            petit = "claude-haiku-5-5" if a in ("Explore", "web-fetch") else modele
            vec = [200, int(9000 * agents[a] * alea.uniform(0.5, 2)), int(500000 * agents[a] * alea.uniform(0.5, 2)), int(60000 * agents[a]), 0]
            tok_agents[a + "|" + petit] = vec
            cle = debut.strftime("%Y-%m-%d") + "|" + petit
            jm[cle] = [x + y for x, y in zip(jm.get(cle, [0] * 5), vec)]
        outils = {o: max(1, int(p * taille * alea.uniform(0.3, 1.5))) for o, p in OUTILS if alea.random() < 0.8}
        hooks = {"PostToolUse:Edit": outils.get("Edit", 0), "Stop : journal.py": alea.randint(3, 25)}
        tok = [sum(v[i] for v in jm.values()) for i in range(5)]
        fin = debut + datetime.timedelta(minutes=int(25 + 90 * taille))
        sortie.append({
            "id": "demo-%s-%03d" % (machine, n), "machine": machine, "titre": alea.choice(TITRES),
            "debut": debut.astimezone().isoformat(), "fin": fin.astimezone().isoformat(),
            "dossier": dossier, "depot": depot, "branche": branche, "entree": "cli", "version": "demo",
            "tok": tok, "jm": jm, "cout_eur": 0, "skills": skills, "tok_skills": tok_skills, "agents": agents,
            "tok_agents": tok_agents, "sous_agents": None, "outils": outils, "hooks": {k: v for k, v in hooks.items() if v},
            "commandes": alea.choice([{}, {}, {"tableau-usage": 1}, {"relais": 1}, {"model": 2}, {"clear": 1}]),
            "invites": alea.randint(3, 40), "messages": alea.randint(20, 400),
        })
    return sortie


def poste(alea, machine, nombre, jours):
    return {"machine": machine, "genere": collecte.time.strftime("%Y-%m-%dT%H:%M:%S"),
            "sessions": sessions(alea, machine, nombre, jours),
            "journal": {"depuis": "2026-01-05T08:12:00", "evenements": {
                "Stop": 412, "SessionStart": 61, "SessionEnd": 58, "PreToolUse · code-review": 14,
                "PreToolUse · Explore": 22, "SubagentStart · Explore": 22, "UserPromptExpansion · relais": 9}},
            "hooks_configures": [
                {"evenement": "PreToolUse", "filtre": "Skill|Agent|Task", "type": "command", "commande": "python journal.py"},
                {"evenement": "PostToolUse", "filtre": "Edit|Write", "type": "command", "commande": "prettier --write"},
                {"evenement": "Stop", "filtre": "", "type": "command", "commande": "python journal.py"}]}


def main():
    alea = random.Random(2026)
    tarifs = collecte.charger_tarifs()
    donnees = {"genere": collecte.time.strftime("%Y-%m-%dT%H:%M:%S"), "tarifs": tarifs,
               "postes": [poste(alea, "poste-fixe", 46, 30), poste(alea, "portable", 14, 30)]}
    with open(os.path.join(ICI, "gabarit.html"), encoding="utf-8") as f:
        page = f.read().replace("__DONNEES__", json.dumps(donnees, ensure_ascii=False).replace("</", "<\\/"))
    cible = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(ICI), "demo.html")
    with open(cible, "w", encoding="utf-8") as f:
        f.write(page)
    print("Page de démonstration : " + cible)


if __name__ == "__main__":
    main()
