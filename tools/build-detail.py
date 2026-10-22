#!/usr/bin/env python3
"""Build the consolidated (central) dashboards from the per-cluster source boards.

The per-cluster boards under dashboards/ are the editable sources. The
consolidated boards (Connectors Detail, Services Detail, Infrastructure
Overview, Content Service (Legacy), and the V2 section of Applications
Overview) are GENERATED from them by this script, as configured in
tools/detail-boards.json. Never edit a generated board by hand: edit the
source board and re-run this script.

Usage:
  python3 tools/build-detail.py            # rebuild every generated board, then validate
  python3 tools/build-detail.py --check    # CI: rebuild in memory, fail if a committed
                                           # generated board differs or a rule is broken
  python3 tools/build-detail.py --fix-sources
                                           # apply the shared rules to the source boards
                                           # in place (small, formatting-preserving edits)

Stdlib only (Python 3.8+). Run from anywhere; paths resolve from the repo root.
"""
import argparse
import copy
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "tools", "detail-boards.json")

# ---------------------------------------------------------------- shared rules

# The datasource variable every Prometheus board carries (main #136/#137):
# Grafana's default datasource, resolved on load, picker hidden. A saved uid
# that does not exist in a given Grafana (e.g. "prometheus-nx") blanks the
# whole board there (a customer cluster with only a local Prometheus).
DATASOURCE_VAR = {
    "name": "datasource",
    "label": "Datasource",
    "type": "datasource",
    "query": "prometheus",
    "refresh": 1,
    "hide": 2,
    "includeAll": False,
    "options": [],
    "current": {"text": "default", "value": "default"},
}
PROM_DS = {"type": "prometheus", "uid": "${datasource}"}

# ConfigMap limit is 1 MiB for the whole object; leave room for metadata.
CONFIGMAP_LIMIT = 1048576 - 8192
CONFIGMAP_PREFIX = "observability-grafana-dashboard-"
DNS1123_SUBDOMAIN = re.compile(r"^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$")
CONFIGMAP_KEY = re.compile(r"^[-._a-zA-Z0-9]+$")

BUILTIN_VARS = {"timeFilter", "interval", "interval_ms"}
VAR_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
VAR_REF = re.compile(
    r"\$\{(" + VAR_NAME + r")((?::[^}]*)?)\}"   # ${name} / ${name:fmt}
    r"|\$(" + VAR_NAME + r")"                    # $name
    r"|\[\[(" + VAR_NAME + r")((?::[^\]]*)?)\]\]"  # [[name]] / [[name:fmt]]
)
# label="..." where the value is a match-everything regex: with = (not =~)
# it matches only the literal string, so the panel shows No data (main #138).
EQ_WILDCARD = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"(\.\*|\.\+)"')
# label="$var" / label="${var}" (any format suffix)
EQ_VAR = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"\$\{?(' + VAR_NAME + r')(?::[^}"]*)?\}?"')


def is_builtin(name):
    return name.startswith("__") or name in BUILTIN_VARS


# ---------------------------------------------------------------- io helpers

def rel(path):
    return os.path.relpath(path, ROOT)


def load(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return json.load(f)


def dump(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def compact(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def dump_generated(dash):
    """One panel / variable per line.

    Fully indented, Connectors Detail is ~1.6 MB, over the 1 MiB ConfigMap
    limit; fully compact it is one line that no diff can show. One line per
    panel keeps it small and still shows which panels a rebuild changed.
    """
    out = ["{"]
    items = list(dash.items())
    for i, (k, v) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        if k == "panels":
            out.append('  "panels": [')
            for j, p in enumerate(v):
                pc = "," if j < len(v) - 1 else ""
                if p.get("type") == "row" and p.get("panels"):
                    head = {kk: vv for kk, vv in p.items() if kk != "panels"}
                    out.append("    " + compact(head)[:-1] + ',"panels":[')
                    kids = p["panels"]
                    for n, c in enumerate(kids):
                        out.append("      " + compact(c) + ("," if n < len(kids) - 1 else ""))
                    out.append("    ]}" + pc)
                else:
                    out.append("    " + compact(p) + pc)
            out.append("  ]" + comma)
        elif k == "templating":
            lst = v.get("list", [])
            out.append('  "templating": {"list": [')
            for j, t in enumerate(lst):
                out.append("    " + compact(t) + ("," if j < len(lst) - 1 else ""))
            out.append("  ]}" + comma)
        else:
            out.append("  %s: %s%s" % (json.dumps(k), compact(v), comma))
    out.append("}")
    return "\n".join(out) + "\n"


def walk_strings(obj, fn):
    """Return a copy of obj with fn applied to every string value (not keys)."""
    if isinstance(obj, str):
        return fn(obj)
    if isinstance(obj, list):
        return [walk_strings(v, fn) for v in obj]
    if isinstance(obj, dict):
        return {k: walk_strings(v, fn) for k, v in obj.items()}
    return obj


def iter_strings(obj, path=""):
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from iter_strings(v, "%s[%d]" % (path, i))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from iter_strings(v, "%s.%s" % (path, k) if path else k)


def all_panels(panels):
    for p in panels:
        yield p
        yield from all_panels(p.get("panels", []))


def template_vars(dash):
    return dash.get("templating", {}).get("list", [])


# ---------------------------------------------------------------- datasources

def is_prom_datasource_var(v):
    return v.get("type") == "datasource" and v.get("query") in ("prometheus", None, "")


def normalize_ds(obj, ds_names):
    """Point every Prometheus datasource reference at ${datasource}.

    ds_names: names of the board's prometheus datasource variables (old names
    like DS_PROMETHEUS included) that collapse into the single ${datasource}.
    """
    refs = {"${%s}" % n for n in ds_names} | {"$%s" % n for n in ds_names}
    if isinstance(obj, list):
        return [normalize_ds(v, ds_names) for v in obj]
    if not isinstance(obj, dict):
        return obj
    out = {}
    for k, v in obj.items():
        if k == "datasource":
            if isinstance(v, str) and (v in refs or v in ("Prometheus", "prometheus")):
                v = dict(PROM_DS)
            elif isinstance(v, dict) and (v.get("uid") in refs or
                                          (v.get("type") == "prometheus" and v.get("uid") in ("Prometheus", "prometheus", None))):
                v = dict(PROM_DS)
            else:
                v = normalize_ds(v, ds_names)
        else:
            v = normalize_ds(v, ds_names)
        out[k] = v
    return out


# ---------------------------------------------------------------- variable rename

def rename_refs(s, mapping):
    """Rewrite $var / ${var[:fmt]} / [[var[:fmt]]] references per mapping."""
    def sub(m):
        if m.group(1) is not None:
            name, fmt = m.group(1), m.group(2) or ""
            if name not in mapping:
                return m.group(0)
            new = mapping[name]
            if fmt == ":queryparam" and new != name:
                # ${x:queryparam} expands to var-<name>=...; a drill-down link
                # to the per-cluster board must keep the target's own name.
                return "var-%s=${%s}" % (name, new)
            return "${%s%s}" % (new, fmt)
        if m.group(3) is not None:
            name = m.group(3)
            return "$" + mapping[name] if name in mapping else m.group(0)
        name, fmt = m.group(4), m.group(5) or ""
        return "[[%s%s]]" % (mapping[name], fmt) if name in mapping else m.group(0)
    return VAR_REF.sub(sub, s)


def var_signature(v):
    """What makes two variable definitions the same picker."""
    keep = ("type", "query", "definition", "regex", "multi", "includeAll", "allValue",
            "refresh", "sort", "options" if v.get("type") == "custom" else None)
    sig = {k: v.get(k) for k in keep if k}
    if isinstance(sig.get("query"), dict):
        sig["query"] = sig["query"].get("query")
    return json.dumps(sig, sort_keys=True)


# ---------------------------------------------------------------- layout

def flatten_source(dash):
    """Return the source's panels as one flat list in expanded-layout coordinates.

    Row panels become small transparent text headers: Grafana does not
    support rows nested inside a collapsed row, so a source's own rows cannot
    stay rows once the source is folded into one.
    """
    out = []
    shift = 0
    for p in dash.get("panels", []):
        p = copy.deepcopy(p)
        gp = p.setdefault("gridPos", {"h": 8, "w": 12, "x": 0, "y": 0})
        if p.get("type") == "row":
            header = {
                "type": "text",
                "title": p.get("title", ""),
                "transparent": True,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": gp.get("y", 0) + shift},
                "options": {"mode": "markdown", "content": "",
                            "code": {"language": "markdown", "showLineNumbers": False, "showMiniMap": False}},
            }
            if p.get("description"):
                header["description"] = p["description"]
            out.append(header)
            children = p.get("panels", []) if p.get("collapsed") else []
            if children:
                top = min(c.get("gridPos", {}).get("y", 0) for c in children)
                bottom = top
                for c in children:
                    c = copy.deepcopy(c)
                    cg = c.setdefault("gridPos", {"h": 8, "w": 12, "x": 0, "y": top})
                    bottom = max(bottom, cg["y"] + cg["h"])
                    cg["y"] = gp.get("y", 0) + shift + 1 + (cg["y"] - top)
                    out.append(c)
                shift += bottom - top
            continue
        gp["y"] = gp.get("y", 0) + shift
        out.append(p)
    if out:
        top = min(p["gridPos"]["y"] for p in out)
        for p in out:
            p["gridPos"]["y"] -= top
    return out


def block_height(panels):
    return max((p["gridPos"]["y"] + p["gridPos"]["h"] for p in panels), default=0)


def strip_panel(p):
    p = dict(p)
    for k in ("scopedVars", "repeatIteration", "repeatPanelId", "libraryPanel"):
        p.pop(k, None)
    return p


# ---------------------------------------------------------------- build

class BuildError(Exception):
    pass


def build_section(board, section, notes):
    """Return (row_children, variables) for one collapsed row."""
    key = section["key"]
    shared = {v["name"] for v in board.get("shared_vars", [])}
    own = set(section.get("own_vars", []))
    unify = section.get("unify", {})
    pickers_hidden = board.get("pickers", "show") == "hide"
    keep = board.get("keep_vars", {})
    wildcard = board.get("wildcard", ".*")

    paths = [s if isinstance(s, str) else s["path"] for s in section["sources"]]
    stems = [os.path.splitext(os.path.basename(p))[0] for p in paths]
    # short name per source: the part after the stem prefix all sources share
    common = os.path.commonprefix(stems) if len(stems) > 1 else ""
    common = common[:common.rfind("-") + 1] if "-" in common else ""
    loaded = []
    for path, stem in zip(paths, stems):
        short = re.sub(r"[^A-Za-z0-9_]", "_", stem[len(common):] or stem)
        loaded.append((path, stem, short, load(path)))

    # Decide one board-level name per (source, variable).
    by_name = {}
    for path, stem, short, dash in loaded:
        for v in template_vars(dash):
            if is_prom_datasource_var(v) or v["name"] in ("datasource", "DS_PROMETHEUS"):
                continue
            if v["name"] in shared and v["name"] not in own:
                continue
            by_name.setdefault(v["name"], []).append((short, stem, v))

    mapping_for = {stem: {} for _, stem, _, _ in loaded}
    variables = []
    for name, defs in by_name.items():
        if name in unify:
            chosen = [d for d in defs if d[1] == unify[name]]
            if not chosen:
                raise BuildError("%s: unify %s names %s, which does not define it" % (key, name, unify[name]))
            groups = [(chosen[0][2], defs, chosen[0][1])]
        else:
            groups = []
            for d in defs:
                for g in groups:
                    if var_signature(g[0]) == var_signature(d[2]):
                        g[1].append(d)
                        break
                else:
                    groups.append((d[2], [d], d[1]))
        for i, (vdef, members, owner) in enumerate(groups):
            new = "%s_%s" % (key, name) if i == 0 else "%s_%s_%s" % (key, members[0][0], name)
            for _, stem, _ in members:
                mapping_for[stem][name] = new
            if len(groups) > 1:
                notes.append("%s: variable %r differs between sources; %s -> %s"
                             % (key, name, ",".join(m[1] for m in members), new))
            variables.append((new, vdef, owner))

    out_vars = []
    wildcarded = set()
    for new, vdef, owner in variables:
        v = copy.deepcopy(vdef)
        v["name"] = new
        label = vdef.get("label") or vdef["name"]
        v["label"] = "%s %s" % (section.get("label", key), label)
        if vdef.get("hide") == 2:
            v["hide"] = 2
        # chained queries reference other variables of the source the definition came from
        m = dict(mapping_for[owner])
        v = walk_strings(v, lambda s: rename_refs(s, m))
        v["name"] = new
        if new in keep:
            v["hide"] = keep[new]
        elif pickers_hidden and v.get("type") != "constant":
            # "hide": the board keeps the shape it had before pickers came back:
            # every per-section variable is a hidden constant matching everything.
            v = {"name": new, "label": v["label"], "type": "constant", "hide": 2, "query": wildcard,
                 "skipUrlSync": True}
            wildcarded.add(new)
        out_vars.append(v)

    # a chained variable goes after the variables it reads
    names = {v["name"] for v in out_vars}

    def deps(v):
        return {m.group(1) or m.group(3) or m.group(4) for _, s in iter_strings(v) for m in VAR_REF.finditer(s)} & names - {v["name"]}
    ordered, placed = [], set()
    while len(ordered) < len(out_vars):
        progress = False
        for v in out_vars:
            if v["name"] not in placed and deps(v) <= placed:
                ordered.append(v)
                placed.add(v["name"])
                progress = True
        if not progress:
            raise BuildError("%s: circular variable references" % key)
    out_vars = ordered

    children = []
    cursor = 0
    for path, stem, short, dash in loaded:
        ds_names = {v["name"] for v in template_vars(dash) if is_prom_datasource_var(v)} | {"datasource", "DS_PROMETHEUS"}
        mapping = dict(mapping_for[stem])
        panels = flatten_source(dash)
        panels = [strip_panel(p) for p in panels]
        panels = normalize_ds(panels, ds_names)
        panels = walk_strings(panels, lambda s: rename_refs(s, mapping))
        if wildcarded:
            # label="$x" with x now matching everything must become =~ (main #138)
            eqv = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"(\$\{?(?:%s)(?::[^}"]*)?\}?)"'
                             % "|".join(sorted(map(re.escape, wildcarded))))
            panels = walk_strings(panels, lambda s: eqv.sub(lambda m: '%s=~"%s"' % (m.group(1), m.group(2)), s))
        panels = relink(panels, board.get("link_map", []))
        for p in all_panels(panels):
            if p.get("repeat") in mapping:
                p["repeat"] = mapping[p["repeat"]]
        title = dash.get("title", stem)
        header = {
            "type": "text",
            "title": "",
            "transparent": True,
            "gridPos": {"h": 2, "w": 24, "x": 0, "y": cursor},
            "options": {
                "mode": "markdown",
                "content": "### %s\nGenerated from `%s` · per-cluster board: [%s](/d/%s)"
                           % (title, path, title, dash.get("uid", "")),
                "code": {"language": "markdown", "showLineNumbers": False, "showMiniMap": False},
            },
        }
        children.append(header)
        base = cursor + 2
        for p in panels:
            p["gridPos"]["y"] += base
            children.append(p)
        cursor = base + block_height(panels)
    return children, out_vars


def build_board(board, notes):
    header = copy.deepcopy(board["header"])
    sources = [s if isinstance(s, str) else s["path"] for sec in board["sections"] for s in sec["sources"]]
    intro = {
        "type": "text",
        "title": "",
        "transparent": True,
        "gridPos": {"h": 3, "w": 24, "x": 0, "y": 0},
        "options": {
            "mode": "markdown",
            "content": board["intro"].rstrip() + "\n\n_Generated by `tools/build-detail.py` from %d per-cluster "
                       "boards. Do not edit this board in Grafana or by hand: edit the source board "
                       "and re-run the script._" % len(sources),
            "code": {"language": "markdown", "showLineNumbers": False, "showMiniMap": False},
        },
    }
    panels = [intro]
    variables = [copy.deepcopy(DATASOURCE_VAR)] + copy.deepcopy(board.get("shared_vars", []))
    y = intro["gridPos"]["h"]
    for sec in board["sections"]:
        children, svars = build_section(board, sec, notes)
        row = {"type": "row", "title": sec["title"], "collapsed": True,
               "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "panels": []}
        for c in children:
            c["gridPos"]["y"] += y + 1
        row["panels"] = children
        panels.append(row)
        variables.extend(svars)
        y += 1
    renumber(panels, 1)
    dash = {"__generated": "GENERATED by tools/build-detail.py from tools/detail-boards.json. "
                           "Edit the source boards, not this file.",
            "__sources": sources}
    dash.update(header)
    dash["panels"] = panels
    dash["templating"] = {"list": variables}
    return dash


def renumber(panels, start):
    n = start
    for p in all_panels(panels):
        p["id"] = n
        n += 1
    return n


def relink(obj, rules):
    rules = [(re.compile(r["match"]), r["replace"]) for r in rules]
    if not rules:
        return obj

    def f(s):
        for rx, rep_ in rules:
            s = rx.sub(rep_, s)
        return s
    return walk_strings(obj, f)


def build_splice(spec, notes):
    """Regenerate the panels after a marker row inside a hand-maintained board."""
    target = load(spec["output"])
    src = load(spec["source"])
    panels = target["panels"]
    idx = [i for i, p in enumerate(panels) if p.get("id") == spec["marker_panel_id"]]
    if not idx:
        raise BuildError("%s: marker panel id %s not found" % (spec["output"], spec["marker_panel_id"]))
    marker = panels[idx[0]]
    target_vars = {v["name"] for v in template_vars(target)}
    src_vars = [v for v in template_vars(src) if not is_prom_datasource_var(v)]
    missing = [v["name"] for v in src_vars if v["name"] not in target_vars]
    if missing:
        raise BuildError("%s: source variables %s are not defined on %s" % (spec["source"], missing, spec["output"]))
    gen = [strip_panel(copy.deepcopy(p)) for p in src["panels"]]
    gen = normalize_ds(gen, {"datasource", "DS_PROMETHEUS"})
    gen = relink(gen, spec.get("link_map", []))
    top = min((p["gridPos"]["y"] for p in gen), default=0)
    base = marker["gridPos"]["y"] + marker["gridPos"]["h"]
    for p in all_panels(gen):
        if "gridPos" in p:
            p["gridPos"]["y"] += base - top
    marker = copy.deepcopy(marker)
    marker["description"] = ("GENERATED below this row by tools/build-detail.py from %s. "
                             "Edit that board, not these panels." % spec["source"])
    renumber(gen, spec["marker_panel_id"] + 1)
    target["panels"] = panels[:idx[0]] + [marker] + gen
    return target


# ---------------------------------------------------------------- validation

def check_board(path, dash, problems, strict, ds_rule=True, warnings=None):
    """strict: generated or source board, held to every shared rule.

    Other boards (hand-maintained or legacy) only get the checks that decide
    whether the sync and Grafana can load them; the rest are warnings.
    """
    if not strict:
        problems = []
    ids = [p.get("id") for p in all_panels(dash.get("panels", []))]
    dup = sorted({i for i in ids if ids.count(i) > 1 and i is not None})
    if dup:
        problems.append("%s: duplicate panel ids %s" % (path, dup[:10]))

    def overlaps(group, where):
        cells = {}
        for p in group:
            g = p.get("gridPos")
            if not g:
                continue
            if g["x"] + g["w"] > 24:
                problems.append("%s: panel %s (%s) is wider than the grid" % (path, p.get("id"), where))
            for yy in range(g["y"], g["y"] + g["h"]):
                for xx in range(g["x"], g["x"] + g["w"]):
                    if (xx, yy) in cells:
                        problems.append("%s: panels %s and %s overlap (%s)" % (path, cells[(xx, yy)], p.get("id"), where))
                        return
                    cells[(xx, yy)] = p.get("id")
    overlaps(dash.get("panels", []), "top level")
    for p in dash.get("panels", []):
        if p.get("type") == "row" and p.get("panels"):
            overlaps(p["panels"], "row %r" % p.get("title"))

    defined = {v["name"] for v in template_vars(dash)}
    vdefs = {v["name"]: v for v in template_vars(dash)}
    for where, s in iter_strings({k: v for k, v in dash.items() if not k.startswith("__")}):
        for m in EQ_WILDCARD.finditer(s):
            problems.append('%s: %s uses %s="%s" (= matches the literal string; use =~)' % (path, where, m.group(1), m.group(2)))
        if not strict:
            continue
        for m in VAR_REF.finditer(s):
            name = m.group(1) or m.group(3) or m.group(4)
            if not is_builtin(name) and name not in defined:
                problems.append("%s: %s references undefined variable $%s" % (path, where, name))
        for m in EQ_VAR.finditer(s):
            v = vdefs.get(m.group(2))
            if v and (v.get("multi") or v.get("includeAll")):
                problems.append('%s: %s uses %s="$%s" but $%s is multi-value/All (use =~)'
                                % (path, where, m.group(1), m.group(2), m.group(2)))
    if strict and ds_rule:
        dsv = [v for v in template_vars(dash) if v.get("name") == "datasource"]
        uses_ds = "${datasource}" in json.dumps(dash)
        if uses_ds and not dsv:
            problems.append("%s: uses ${datasource} but defines no datasource variable" % path)
        for v in dsv:
            cur = (v.get("current") or {}).get("value")
            if v.get("type") != "datasource" or v.get("query") != "prometheus" or cur not in ("default", None, "") \
                    or v.get("hide") != 2:
                problems.append("%s: datasource variable must be type datasource, query prometheus, current "
                                "'default', hide 2 (run --fix-sources)" % path)
    if not strict and warnings is not None:
        warnings.extend(problems)


def check_tree(problems, generated, sources, warnings):
    uids, titles = {}, {}
    for dp, _, files in os.walk(os.path.join(ROOT, "dashboards")):
        for f in sorted(files):
            if not f.endswith(".json"):
                continue
            full = os.path.join(dp, f)
            path = rel(full)
            raw = open(full, "rb").read()
            try:
                dash = json.loads(raw.decode("utf-8"))
            except ValueError as e:
                problems.append("%s: invalid JSON: %s" % (path, e))
                continue
            splice = False
            if path in generated:
                dash, dumper, splice = generated[path]
                raw = dumper(dash).encode("utf-8")
            if len(raw) > CONFIGMAP_LIMIT:
                problems.append("%s: %d bytes, over the ConfigMap limit (%d)" % (path, len(raw), CONFIGMAP_LIMIT))
            # mirror grafana-dashboards-sync: name = prefix + path without .json, / -> -, lowercased
            cm = CONFIGMAP_PREFIX + path[:-5].replace("/", "-").lower()
            if len(cm) > 253 or not DNS1123_SUBDOMAIN.match(cm):
                problems.append("%s: ConfigMap name %r is not a valid Kubernetes name" % (path, cm))
            if not CONFIGMAP_KEY.match(f):
                problems.append("%s: file name is not a valid ConfigMap key" % path)
            uid = dash.get("uid")
            if not uid:
                (problems if path in generated or path in sources else warnings).append(
                    "%s: dashboard has no uid (Grafana assigns one)" % path)
            elif len(uid) > 40:
                problems.append("%s: uid %r longer than 40 characters" % (path, uid))
            elif uid in uids:
                problems.append("%s: uid %r already used by %s" % (path, uid, uids[uid]))
            else:
                uids[uid] = path
            tkey = (dash.get("folderUid") or "", dash.get("title"))
            if tkey in titles:
                problems.append("%s: title %r already used in the same folder by %s" % (path, tkey[1], titles[tkey]))
            titles[tkey] = path
            check_board(path, dash, problems, strict=path in generated or path in sources,
                        ds_rule=not splice, warnings=warnings)


# ---------------------------------------------------------------- source fixer

class Span:
    __slots__ = ("start", "end", "children")

    def __init__(self, start, end, children):
        self.start, self.end, self.children = start, end, children


def parse_spans(text):
    """Minimal JSON parser that records where every value starts and ends."""
    ws = " \t\r\n"
    pos = [0]

    def skip():
        while pos[0] < len(text) and text[pos[0]] in ws:
            pos[0] += 1

    def value():
        skip()
        start = pos[0]
        c = text[start]
        if c == "{":
            pos[0] += 1
            kids = {}
            skip()
            if text[pos[0]] == "}":
                pos[0] += 1
                return Span(start, pos[0], kids)
            while True:
                skip()
                k = json.loads(text[pos[0]:string_end(pos[0])])
                pos[0] = string_end(pos[0])
                skip()
                pos[0] += 1  # :
                kids[k] = value()
                skip()
                if text[pos[0]] == ",":
                    pos[0] += 1
                    continue
                pos[0] += 1  # }
                return Span(start, pos[0], kids)
        if c == "[":
            pos[0] += 1
            kids = []
            skip()
            if text[pos[0]] == "]":
                pos[0] += 1
                return Span(start, pos[0], kids)
            while True:
                kids.append(value())
                skip()
                if text[pos[0]] == ",":
                    pos[0] += 1
                    continue
                pos[0] += 1
                return Span(start, pos[0], kids)
        if c == '"':
            pos[0] = string_end(start)
            return Span(start, pos[0], None)
        m = re.compile(r"-?\d+(\.\d+)?([eE][-+]?\d+)?|true|false|null").match(text, start)
        pos[0] = m.end()
        return Span(start, pos[0], None)

    def string_end(i):
        i += 1
        while text[i] != '"':
            i += 2 if text[i] == "\\" else 1
        return i + 1

    return value()


def fix_source(path):
    """Apply the shared rules to one source board with small text edits."""
    full = os.path.join(ROOT, path)
    text = open(full, encoding="utf-8").read()
    dash = json.loads(text)
    edits = []  # (start, end, replacement)
    root = parse_spans(text)
    tl = root.children.get("templating")
    lst = tl.children.get("list") if tl else None

    def indent_at(i):
        line_start = text.rfind("\n", 0, i) + 1
        return i - line_start

    def render(obj, at):
        pad = " " * indent_at(at)
        ascii_ = "\\u" in text
        s = json.dumps(obj, indent=2, ensure_ascii=ascii_)
        return s.replace("\n", "\n" + pad)

    literal = list(re.finditer(r'"datasource":\s*"(Prometheus|prometheus)"', text))
    uses_ds = '"${datasource}"' in text or '"$datasource"' in text or bool(literal)
    vars_ = template_vars(dash)
    has_ds = any(v.get("name") == "datasource" for v in vars_)
    if lst is not None:
        for v, span in zip(vars_, lst.children):
            if v.get("name") == "datasource":
                want = dict(DATASOURCE_VAR)
                if v.get("label"):
                    want["label"] = v["label"]
                if v != want:
                    edits.append((span.start, span.end, render(want, span.start)))
        if uses_ds and not has_ds:
            if lst.children:
                first = lst.children[0]
                edits.append((first.start, first.start, render(dict(DATASOURCE_VAR), first.start) + ",\n" +
                              " " * indent_at(first.start)))
            else:
                pad = " " * (indent_at(lst.start) + 2)
                edits.append((lst.start, lst.end, "[\n" + pad + render(dict(DATASOURCE_VAR), 0).replace(
                    "\n", "\n" + pad) + "\n" + " " * indent_at(lst.start) + "]"))
    # literal "Prometheus" datasource strings -> the variable
    for m in literal:
        edits.append((m.start(1) - 1, m.end(1) + 1, json.dumps(PROM_DS)))
    if uses_ds and not has_ds and lst is None:
        raise BuildError("%s: no template list to add the datasource variable to" % path)
    # label=".*" -> label=~".*"; label="$multi" -> label=~"$multi"
    multi = {v["name"] for v in vars_ if v.get("multi") or v.get("includeAll")}
    for m in re.finditer(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\\"(\.\*|\.\+)\\"', text):
        edits.append((m.start(), m.end(), m.group(0).replace("=", "=~", 1)))
    for m in re.finditer(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\\"\$\{?(' + VAR_NAME + r')(?::[^}"\\]*)?\}?\\"', text):
        if m.group(2) in multi:
            edits.append((m.start(), m.end(), m.group(0).replace("=", "=~", 1)))
    if not edits:
        return False
    edits.sort()
    out, last = [], 0
    for s, e, r in edits:
        if s < last:
            continue
        out.append(text[last:s])
        out.append(r)
        last = e
    out.append(text[last:])
    new = "".join(out)
    json.loads(new)
    with open(full, "w", encoding="utf-8") as f:
        f.write(new)
    return True


# ---------------------------------------------------------------- main

def source_paths(manifest):
    paths = set()
    for b in manifest["boards"]:
        if b.get("mode") == "splice":
            paths.add(b["source"])
        else:
            for sec in b["sections"]:
                for s in sec["sources"]:
                    paths.add(s if isinstance(s, str) else s["path"])
    return paths


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="do not write; fail on drift or rule violations")
    ap.add_argument("--fix-sources", action="store_true", help="apply the shared rules to the source boards")
    ap.add_argument("-v", "--verbose", action="store_true", help="print variable-naming decisions")
    args = ap.parse_args()

    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    sources = source_paths(manifest) | set(manifest.get("extra_sources", []))
    for s in sorted(sources):
        if not os.path.exists(os.path.join(ROOT, s)):
            print("ERROR: source %s does not exist" % s)
            return 1

    if args.fix_sources:
        changed = [s for s in sorted(sources) if fix_source(s)]
        for s in changed:
            print("fixed  %s" % s)
        print("%d source board(s) changed" % len(changed))

    notes, generated = [], {}
    try:
        for b in manifest["boards"]:
            out = b["output"]
            if out in sources:
                raise BuildError("%s is both a source and a generated board" % out)
            if b.get("mode") == "splice":
                generated[out] = (build_splice(b, notes), dump, True)
            else:
                generated[out] = (build_board(b, notes), dump_generated, False)
    except BuildError as e:
        print("ERROR: %s" % e)
        return 1

    drift = []
    for out, (dash, dumper, _) in generated.items():
        text = dumper(dash)
        full = os.path.join(ROOT, out)
        current = open(full, encoding="utf-8").read() if os.path.exists(full) else None
        if current != text:
            drift.append(out)
            if not args.check:
                with open(full, "w", encoding="utf-8") as f:
                    f.write(text)
        n = sum(1 for _ in all_panels(dash["panels"]))
        size = len(text.encode())
        print("%-8s %-52s %4d panels %8d bytes (%d%% of the ConfigMap limit)"
              % ("drift" if (args.check and current != text) else ("wrote" if current != text else "ok"),
                 out, n, size, 100 * size // CONFIGMAP_LIMIT))
        if size > 0.9 * CONFIGMAP_LIMIT:
            print("WARN: %s is above 90%% of the ConfigMap limit; split a section into its own board "
                  "in tools/detail-boards.json before it grows past it" % out)
    if args.verbose:
        for n in notes:
            print("note: %s" % n)

    problems, warnings = [], []
    check_tree(problems, generated, sources, warnings)
    for w in warnings:
        print("warn: %s" % w)
    for p in problems:
        print("FAIL: %s" % p)
    if args.check and drift:
        print("FAIL: generated board(s) out of date: %s. Run python3 tools/build-detail.py and commit the result."
              % ", ".join(drift))
    ok = not problems and not (args.check and drift)
    print("OK" if ok else "%d problem(s)" % (len(problems) + (1 if args.check and drift else 0)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
