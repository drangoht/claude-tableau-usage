#!/usr/bin/env python3
"""Installe (ou retire) le hook de journalisation dans ~/.claude/settings.json.

  python installer.py                 ajoute les hooks, puis génère le tableau
  python installer.py --desinstaller  retire les hooks (les données sont conservées)

Rejouable sans risque : les entrées déjà posées par ce script sont remplacées,
les autres hooks ne sont pas touchés. Une copie de settings.json est gardée dans
settings.json.avant-tableau-usage lors de la première installation.
"""
import json
import os
import shutil
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
JOURNAL = os.path.join(ICI, "journal.py").replace("\\", "/")
COLLECTE = os.path.join(ICI, "collecte.py")
REGLAGES = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
PYTHON = sys.executable.replace("\\", "/")

# Événement -> filtre (None = pas de filtre). Tous asynchrones : Claude n'attend jamais le hook.
EVENEMENTS = {
    "PreToolUse": "Skill|Agent|Task",   # chargement d'un skill, lancement d'un sous-agent
    "UserPromptExpansion": None,        # commande « / » tapée par l'utilisateur
    "SubagentStart": None,
    "SessionStart": None,
    "SessionEnd": None,                 # régénère le tableau
    "Stop": None,                       # régénère le tableau s'il a plus de 10 minutes
}


def est_des_notres(groupe):
    return any("tableau-usage" in " ".join([str(h.get("command", ""))] + [str(a) for a in h.get("args") or []])
               and "journal.py" in " ".join(str(a) for a in h.get("args") or [])
               for h in groupe.get("hooks") or [])


def main():
    retirer = "--desinstaller" in sys.argv
    reglages = {}
    if os.path.exists(REGLAGES):
        with open(REGLAGES, encoding="utf-8") as f:
            reglages = json.load(f)  # un settings.json invalide arrête tout : on ne l'écrase pas
        copie = REGLAGES + ".avant-tableau-usage"
        if not os.path.exists(copie):
            shutil.copy2(REGLAGES, copie)
    hooks = reglages.setdefault("hooks", {})
    for evenement in list(hooks):
        hooks[evenement] = [g for g in hooks[evenement] if not est_des_notres(g)]
        if not hooks[evenement]:
            del hooks[evenement]
    if not retirer:
        for evenement, filtre in EVENEMENTS.items():
            groupe = {"hooks": [{"type": "command", "command": PYTHON, "args": [JOURNAL], "async": True, "timeout": 10}]}
            if filtre:
                groupe = {"matcher": filtre, **groupe}
            hooks.setdefault(evenement, []).append(groupe)
    if not hooks:
        del reglages["hooks"]
    os.makedirs(os.path.dirname(REGLAGES), exist_ok=True)
    with open(REGLAGES + ".tmp", "w", encoding="utf-8", newline="\n") as f:
        json.dump(reglages, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(REGLAGES + ".tmp", REGLAGES)

    if retirer:
        print("Hooks retirés de " + REGLAGES + ". Les données restent dans ~/.claude/tableau-usage.")
        return 0
    print("Hooks installés dans " + REGLAGES + " (" + ", ".join(EVENEMENTS) + ").")
    print("Ils seront actifs dans les sessions Claude Code ouvertes à partir de maintenant.")
    attendu = os.path.join(os.path.expanduser("~"), ".claude", "skills", "tableau-usage", "scripts")
    if os.path.normcase(os.path.normpath(ICI)) != os.path.normcase(os.path.normpath(attendu)):
        print("Note : pour disposer de la commande /tableau-usage, placez ce dossier dans ~/.claude/skills/tableau-usage.")
    return subprocess.call([sys.executable, COLLECTE])


if __name__ == "__main__":
    sys.exit(main())
