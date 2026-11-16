#!/usr/bin/env python3
"""Hook de journalisation Claude Code (0 token : ne renvoie rien au modèle).

Reçoit l'événement du hook en JSON sur stdin, ajoute une ligne à
~/.claude/tableau-usage/journal.jsonl, et relance en tâche de fond la mise à
jour du tableau de bord quand il est périmé. Ne doit jamais faire échouer
Claude Code : toute erreur est avalée et le code de sortie est toujours 0.
"""
import json
import os
import socket
import subprocess
import sys
import time

RACINE = os.path.join(os.path.expanduser("~"), ".claude", "tableau-usage")
JOURNAL = os.path.join(RACINE, "journal.jsonl")
TABLEAU = os.path.join(RACINE, "tableau.html")
COLLECTE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "collecte.py")
PEREMPTION_S = 600  # sur Stop : pas plus d'une régénération toutes les 10 min


def ligne(evt):
    nom = evt.get("hook_event_name") or "?"
    entree = evt.get("tool_input") if isinstance(evt.get("tool_input"), dict) else {}
    l = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "machine": socket.gethostname(),
        "ev": nom,
        "sid": evt.get("session_id"),
        "cwd": evt.get("cwd"),
    }
    outil = evt.get("tool_name")
    if outil:
        l["outil"] = outil
    if outil == "Skill":
        l["skill"] = entree.get("skill")
    elif outil in ("Agent", "Task"):
        l["agent"] = entree.get("subagent_type") or "general-purpose"
        if entree.get("model"):
            l["modele"] = entree.get("model")
    if nom in ("SubagentStart", "SubagentStop"):
        l["agent"] = evt.get("agent_type")
    if nom == "UserPromptExpansion":
        l["commande"] = evt.get("command_name")
        l["type"] = evt.get("expansion_type")
    if nom == "SessionStart":
        l["source"] = evt.get("source")
        l["modele"] = evt.get("model")
    if nom == "SessionEnd":
        l["raison"] = evt.get("reason")
    return {k: v for k, v in l.items() if v is not None}


def relancer_collecte(nom):
    if nom not in ("Stop", "SessionEnd"):
        return
    if nom == "Stop":
        try:
            if time.time() - os.path.getmtime(TABLEAU) < PEREMPTION_S:
                return
        except OSError:
            pass
    options = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        options["creationflags"] = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
    else:
        options["start_new_session"] = True
    subprocess.Popen([sys.executable, COLLECTE, "--silencieux"], **options)


def main():
    try:
        evt = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
        if not isinstance(evt, dict):
            return
        os.makedirs(RACINE, exist_ok=True)
        with open(JOURNAL, "a", encoding="utf-8") as f:
            f.write(json.dumps(ligne(evt), ensure_ascii=False) + "\n")
        relancer_collecte(evt.get("hook_event_name"))
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
