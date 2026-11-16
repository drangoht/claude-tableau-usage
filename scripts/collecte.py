#!/usr/bin/env python3
"""Collecte l'usage local de Claude Code et génère le tableau de bord (0 token).

Lit les transcripts ~/.claude/projects/**/*.jsonl (tokens, modèles, dossiers,
skills, agents, hooks, outils), le journal du hook et les réglages, puis écrit :
  ~/.claude/tableau-usage/tableau.html           page autonome, hors ligne
  ~/.claude/tableau-usage/donnees-<machine>.json export à copier sur un autre poste
Les fichiers déposés dans ~/.claude/tableau-usage/import/ (exports d'autres
postes) sont fusionnés dans la page.

Incrémental : seuls les transcripts modifiés depuis le dernier passage sont
relus ; le résumé des sessions reste en cache même après la purge des
transcripts par Claude Code (cleanupPeriodDays).

Python 3.8+, bibliothèque standard uniquement.
  --ouvrir      ouvre la page dans le navigateur
  --complet     ignore le cache et relit tout
  --silencieux  n'affiche rien (appel depuis le hook)
"""
import argparse
import collections
import datetime
import glob
import json
import os
import re
import socket
import sys
import time

CLAUDE = os.path.join(os.path.expanduser("~"), ".claude")
PROJETS = os.path.join(CLAUDE, "projects")
RACINE = os.path.join(CLAUDE, "tableau-usage")
CACHE = os.path.join(RACINE, "cache.json")
VERROU = os.path.join(RACINE, "collecte.verrou")
GABARIT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gabarit.html")
VERSION_CACHE = 4
MACHINE = socket.gethostname()

MARQUEURS = ('"type":"assistant"', '"type":"user"', '"type":"attachment"', '"type":"system"',
             '"type":"custom-title"', '"type":"ai-title"')
RE_COMMANDE = re.compile(r"<command-name>\s*/?([^<\s]+)\s*</command-name>")
RE_ORIGIN = re.compile(r'\[remote "origin"\][^\[]*?url\s*=\s*(\S+)', re.S)
RE_DEPOT = re.compile(r"[:/]([^/:]+/[^/]+?)(?:\.git)?/?$")
RE_ESPACES = re.compile(r"\s+")


def jour_local(ts):
    try:
        d = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return d.astimezone().strftime("%Y-%m-%d")
    except Exception:
        return (ts or "")[:10]


N = 5  # vecteur de tokens : [entrée, sortie, cache lu, cache écrit, dont cache écrit pour 1 h]


def ajouter(dico, cle, vec):
    cible = dico.setdefault(cle, [0] * N)
    for i in range(N):
        cible[i] += vec[i]


def charger_tarifs():
    """Tarifs par modèle : ~/.claude/tableau-usage/tarifs.json s'il existe, sinon celui du skill."""
    for chemin in (os.path.join(RACINE, "tarifs.json"),
                   os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tarifs.json")):
        t = lire_json(chemin, None)
        if isinstance(t, dict) and isinstance(t.get("modeles"), dict):
            return t
    return {"modeles": {}, "usd_par_eur": 1}


def cout_eur(tarifs, modele, vec):
    """Coût estimé en euros d'un vecteur de tokens, au tarif public de l'API (0 si le modèle est inconnu)."""
    prefixes = [p for p in tarifs["modeles"] if modele.startswith(p)]
    if not prefixes:
        return 0.0
    p = tarifs["modeles"][max(prefixes, key=len)]
    ecrit = (vec[3] - vec[4]) * tarifs.get("cache_ecrit_5m_x_entree", 1.25) + vec[4] * tarifs.get("cache_ecrit_1h_x_entree", 2)
    usd = (vec[0] * p["entree"] + vec[1] * p["sortie"] + vec[2] * p["cache_lu"] + ecrit * p["entree"]) / 1e6
    return usd / (tarifs.get("usd_par_eur") or 1)


def texte_utilisateur(contenu):
    """Texte tapé par l'utilisateur, ou None si le message n'est qu'un résultat d'outil."""
    if isinstance(contenu, str):
        return contenu
    if isinstance(contenu, list):
        morceaux = [b.get("text", "") for b in contenu if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(morceaux) if morceaux else None
    return None


def analyser(chemin, sous_agent):
    """Résume un transcript : tokens par modèle et par jour, outils, skills, agents, hooks."""
    messages = {}      # id de message -> [modèle, jour, entrée, sortie, cache lu, cache écrit, skill, agent]
    outils_vus = set()
    outils, skills, agents, hooks, commandes = (collections.Counter() for _ in range(5))
    dossiers, branches = collections.Counter(), collections.Counter()
    r = {"debut": None, "fin": None, "titre": None, "amorce": None, "invites": 0,
         "entree": None, "version": None, "sid": None}

    with open(chemin, encoding="utf-8", errors="replace") as f:
        for brut in f:
            if not any(m in brut for m in MARQUEURS):
                continue
            try:
                d = json.loads(brut)
            except ValueError:
                continue
            t = d.get("type")
            if t == "custom-title":
                r["titre"] = d.get("customTitle") or r["titre"]
                continue
            if t == "ai-title":
                r["titre"] = r["titre"] or d.get("aiTitle")
                continue
            ts = d.get("timestamp")
            if ts:
                if r["debut"] is None or ts < r["debut"]:
                    r["debut"] = ts
                if r["fin"] is None or ts > r["fin"]:
                    r["fin"] = ts
            if d.get("cwd"):
                dossiers[d["cwd"]] += 1
            if d.get("gitBranch"):
                branches[d["gitBranch"]] += 1
            r["entree"] = d.get("entrypoint") or r["entree"]
            r["version"] = d.get("version") or r["version"]
            r["sid"] = r["sid"] or d.get("sessionId")
            msg = d.get("message") if isinstance(d.get("message"), dict) else {}

            if t == "assistant":
                u = msg.get("usage")
                modele = msg.get("model")
                if isinstance(u, dict) and modele and modele != "<synthetic>":
                    cle = msg.get("id") or d.get("uuid")
                    detail = u.get("cache_creation") if isinstance(u.get("cache_creation"), dict) else {}
                    vec = [u.get("input_tokens") or 0, u.get("output_tokens") or 0,
                           u.get("cache_read_input_tokens") or 0, u.get("cache_creation_input_tokens") or 0,
                           detail.get("ephemeral_1h_input_tokens") or 0]
                    m = messages.get(cle)
                    if m is None:
                        messages[cle] = [modele, jour_local(ts)] + vec + [d.get("attributionSkill"), d.get("attributionAgent")]
                    else:  # même message réparti sur plusieurs lignes : on garde le maximum
                        for i in range(N):
                            m[2 + i] = max(m[2 + i], vec[i])
                        m[2 + N] = m[2 + N] or d.get("attributionSkill")
                        m[3 + N] = m[3 + N] or d.get("attributionAgent")
                for b in msg.get("content") or []:
                    if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                        continue
                    if b.get("id") in outils_vus:
                        continue
                    outils_vus.add(b.get("id"))
                    nom = b.get("name") or "?"
                    outils[nom] += 1
                    e = b.get("input") if isinstance(b.get("input"), dict) else {}
                    if nom == "Skill" and e.get("skill"):
                        skills[e["skill"]] += 1
                    elif nom in ("Agent", "Task"):
                        agents[e.get("subagent_type") or "general-purpose"] += 1
            elif t == "user" and not sous_agent and not d.get("isMeta"):
                txt = texte_utilisateur(msg.get("content"))
                if txt is None:
                    continue
                cmd = RE_COMMANDE.search(txt)
                if cmd:
                    commandes[cmd.group(1)] += 1
                elif not txt.lstrip().startswith("<"):
                    r["invites"] += 1
                    if r["amorce"] is None:
                        r["amorce"] = RE_ESPACES.sub(" ", txt).strip()[:110]
            elif t == "attachment":
                a = d.get("attachment") if isinstance(d.get("attachment"), dict) else {}
                if str(a.get("type", "")).startswith("hook_"):
                    hooks[a.get("hookName") or a.get("hookEvent") or a.get("type")] += 1
            elif t == "system" and d.get("subtype") == "stop_hook_summary":
                for info in d.get("hookInfos") or []:
                    c = (info or {}).get("command") or "?"
                    hooks["Stop (interne à l'app)" if c == "callback" else "Stop : " + c[:60]] += 1

    modeles, jours, jm, par_skill, par_agent = {}, {}, {}, {}, {}
    for m in messages.values():
        modele, jour, vec, skill, agent = m[0], m[1], m[2:2 + N], m[2 + N], m[3 + N]
        ajouter(modeles, modele, vec)
        ajouter(jours, jour, vec)
        ajouter(jm, jour + "|" + modele, vec)
        if skill:  # clé « nom|modèle » : le modèle sert à chiffrer le coût
            ajouter(par_skill, skill + "|" + modele, vec)
        if agent:
            ajouter(par_agent, agent + "|" + modele, vec)
    r.update(modeles=modeles, jours=jours, jm=jm, par_skill=par_skill, par_agent=par_agent,
             messages=len(messages), outils=dict(outils), skills=dict(skills), agents=dict(agents),
             hooks=dict(hooks), commandes=dict(commandes),
             dossiers=[c for c, _ in dossiers.most_common(8)],
             branche=branches.most_common(1)[0][0] if branches else None)
    return r


def depot_de(dossier):
    """Dépôt git d'un dossier : nom (owner/depot si un remote origin existe) et racine."""
    courant = dossier
    for _ in range(40):
        git = os.path.join(courant, ".git")
        if os.path.isfile(git):  # worktree : « gitdir: <racine>/.git/worktrees/<nom> »
            try:
                cible = open(git, encoding="utf-8", errors="replace").read().split(":", 1)[1].strip()
                racine = re.split(r"[\\/]\.git[\\/]", cible)[0]
                if os.path.isdir(os.path.join(racine, ".git")):
                    courant, git = racine, os.path.join(racine, ".git")
            except Exception:
                pass
        if os.path.isdir(git):
            nom = os.path.basename(courant.rstrip("\\/")) or courant
            try:
                conf = open(os.path.join(git, "config"), encoding="utf-8", errors="replace").read()
                m = RE_ORIGIN.search(conf)
                if m:
                    url = re.sub(r"//[^@/]*@", "//", m.group(1))  # jamais d'identifiants dans la page
                    n = RE_DEPOT.search(url)
                    if n:
                        nom = n.group(1)
            except OSError:
                pass
            return {"nom": nom, "racine": courant}
        parent = os.path.dirname(courant.rstrip("\\/"))
        if not parent or parent == courant:
            break
        courant = parent
    return None


def fusionner(cible, source, cles_vec=("modeles", "jours", "jm", "par_skill", "par_agent"),
              cles_cpt=("outils", "skills", "agents", "hooks", "commandes")):
    for c in cles_vec:
        for k, v in source.get(c, {}).items():
            ajouter(cible.setdefault(c, {}), k, v)
    for c in cles_cpt:
        for k, v in source.get(c, {}).items():
            cible.setdefault(c, {})[k] = cible.get(c, {}).get(k, 0) + v
    cible["messages"] = cible.get("messages", 0) + source.get("messages", 0)


def lire_json(chemin, defaut):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return defaut


def ecrire(chemin, texte):
    tmp = chemin + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(texte)
    os.replace(tmp, chemin)


def sessions_locales(complet, tarifs):
    cache = lire_json(CACHE, {})
    if cache.get("v") != VERSION_CACHE:
        cache = {"v": VERSION_CACHE, "fichiers": {}, "depots": cache.get("depots", {})}
    if complet:  # tout relire, sans perdre les sessions dont le transcript a déjà été purgé
        for f in cache["fichiers"].values():
            f["mt"] = -1
        cache["depots"] = {}
    fichiers, relus = cache["fichiers"], 0
    for chemin in glob.glob(os.path.join(PROJETS, "*", "*.jsonl")) + \
            glob.glob(os.path.join(PROJETS, "*", "*", "subagents", "*.jsonl")):
        rel = os.path.relpath(chemin, PROJETS).replace("\\", "/")
        try:
            st = os.stat(chemin)
        except OSError:
            continue
        connu = fichiers.get(rel)
        if connu and connu["mt"] == int(st.st_mtime) and connu["sz"] == st.st_size:
            continue
        try:
            resume = analyser(chemin, "/subagents/" in rel)
        except OSError:
            continue
        fichiers[rel] = {"mt": int(st.st_mtime), "sz": st.st_size, "r": resume}
        relus += 1

    # Les transcripts de sous-agents sont rattachés à la session qui les a lancés.
    sessions, enfants = {}, []
    for rel, f in fichiers.items():
        parties = rel.split("/")
        if len(parties) == 2:
            sessions[parties[1][:-6]] = (parties[0], json.loads(json.dumps(f["r"])))
        else:
            enfants.append((parties[1], f["r"]))
    for parent, r in enfants:
        cible = sessions.get(parent) or sessions.get(r.get("sid"))
        if not cible:
            continue
        s = cible[1]
        fusionner(s, r)
        tot = s.setdefault("sous_agents", [0] * N)
        for v in r.get("modeles", {}).values():
            for i in range(N):
                tot[i] += v[i]

    depots, sortie = cache.setdefault("depots", {}), []
    for sid, (projet, r) in sessions.items():
        if not r.get("messages") or not r.get("debut"):
            continue
        dossier = (r.get("dossiers") or [None])[0]
        if dossier and (dossier not in depots or (depots[dossier] is None and os.path.isdir(dossier))):
            depots[dossier] = depot_de(dossier) if os.path.isdir(dossier) else None
        dep = depots.get(dossier) if dossier else None
        sans_dossier = bool(dossier) and "scratch-workspaces" in dossier
        tok = [0] * N
        for v in r["modeles"].values():
            for i in range(N):
                tok[i] += v[i]
        sortie.append({
            "id": sid, "machine": MACHINE,
            "titre": r.get("titre") or r.get("amorce") or "(sans titre)",
            "debut": r["debut"], "fin": r["fin"],
            "dossier": "(sans dossier)" if sans_dossier else (dossier or projet),
            "depot": None if sans_dossier else (dep or {}).get("nom"),
            "branche": r.get("branche"), "entree": r.get("entree"), "version": r.get("version"),
            "tok": tok, "jm": r["jm"],  # jm : « jour|modèle » -> vecteur de tokens (voir N)
            "cout_eur": round(sum(cout_eur(tarifs, k.split("|", 1)[1], v) for k, v in r["jm"].items()), 4),
            "skills": r["skills"], "tok_skills": r["par_skill"],
            "agents": r["agents"], "tok_agents": r["par_agent"], "sous_agents": r.get("sous_agents"),
            "outils": r["outils"], "hooks": r["hooks"], "commandes": r["commandes"],
            "invites": r["invites"], "messages": r["messages"],
        })
    ecrire(CACHE, json.dumps(cache, ensure_ascii=False, separators=(",", ":")))
    return sortie, relus


def journal_local():
    """Événements écrits par journal.py, comptés par type."""
    cpt, premier = collections.Counter(), None
    try:
        with open(os.path.join(RACINE, "journal.jsonl"), encoding="utf-8", errors="replace") as f:
            for brut in f:
                try:
                    l = json.loads(brut)
                except ValueError:
                    continue
                detail = l.get("skill") or l.get("agent") or l.get("commande") or l.get("outil")
                cpt[l.get("ev", "?") + (" · " + str(detail) if detail else "")] += 1
                premier = premier or l.get("ts")
    except OSError:
        pass
    return {"depuis": premier, "evenements": dict(cpt)}


def hooks_configures():
    liste = []
    reglages = lire_json(os.path.join(CLAUDE, "settings.json"), {})
    for evenement, groupes in (reglages.get("hooks") or {}).items():
        for g in groupes or []:
            for h in g.get("hooks") or []:
                cmd = " ".join([str(h.get("command") or h.get("prompt") or h.get("url") or h.get("tool") or "")]
                               + [os.path.basename(str(a)) for a in h.get("args") or []])
                liste.append({"evenement": evenement, "filtre": g.get("matcher") or "", "type": h.get("type"),
                              "commande": cmd[:120]})
    return liste


def main():
    ap = argparse.ArgumentParser(description="Met à jour le tableau de bord d'usage de Claude Code.")
    ap.add_argument("--ouvrir", action="store_true")
    ap.add_argument("--complet", action="store_true")
    ap.add_argument("--silencieux", action="store_true")
    a = ap.parse_args()
    os.makedirs(os.path.join(RACINE, "import"), exist_ok=True)

    try:  # une seule collecte à la fois (plusieurs sessions peuvent finir ensemble)
        if time.time() - os.path.getmtime(VERROU) < 300:
            return 0
    except OSError:
        pass
    open(VERROU, "w").close()
    try:
        tarifs = charger_tarifs()
        sessions, relus = sessions_locales(a.complet, tarifs)
        genere = time.strftime("%Y-%m-%dT%H:%M:%S")
        local = {"machine": MACHINE, "genere": genere, "sessions": sessions, "tarifs": tarifs,
                 "journal": journal_local(), "hooks_configures": hooks_configures()}
        ecrire(os.path.join(RACINE, "donnees-%s.json" % MACHINE),
               json.dumps(local, ensure_ascii=False, separators=(",", ":")))

        postes = [local]
        for chemin in sorted(glob.glob(os.path.join(RACINE, "import", "*.json"))):
            autre = lire_json(chemin, None)
            if isinstance(autre, dict) and autre.get("machine") and autre["machine"] != MACHINE \
                    and isinstance(autre.get("sessions"), list):
                postes.append(autre)
        donnees = json.dumps({"genere": genere, "tarifs": tarifs, "postes": postes}, ensure_ascii=False,
                             separators=(",", ":")).replace("</", "<\\/").replace("<!--", "<\\u0021--")
        with open(GABARIT, encoding="utf-8") as f:
            page = f.read().replace("__DONNEES__", donnees)
        tableau = os.path.join(RACINE, "tableau.html")
        ecrire(tableau, page)
    finally:
        try:
            os.remove(VERROU)
        except OSError:
            pass

    if not a.silencieux:
        tok = [sum(s["tok"][i] for s in sessions) for i in range(4)]
        print("Tableau à jour : %d sessions sur %s (%d transcripts relus), %d poste(s)." %
              (len(sessions), MACHINE, relus, len(postes)))
        print("Tokens : entrée %d, sortie %d, cache écrit %d, cache lu %d." % (tok[0], tok[1], tok[3], tok[2]))
        print("Coût estimé au tarif public de l'API : %.2f € (indicatif ; un abonnement n'est pas facturé au token)." %
              sum(s["cout_eur"] for s in sessions))
        print("Page : " + tableau)
    if a.ouvrir:
        import webbrowser
        webbrowser.open("file:///" + tableau.replace("\\", "/"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
