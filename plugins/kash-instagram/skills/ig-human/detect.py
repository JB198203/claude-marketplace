#!/usr/bin/env python3
"""
detect.py - a five-check panel that scores how machine-written a draft looks.

What this is:  five local heuristics modelled on the signals public AI
detectors actually measure - sentence-length variation, concreteness, stock
vocabulary, typographic fingerprint, and voice. Every score is computed on
your machine from the text alone. Nothing is uploaded.

What this is NOT:  GPTZero, Originality, Copyleaks, Winston or Turnitin.
It does not call their APIs and it cannot promise their verdict. It catches
the things they all key on, which is why fixing them tends to move their
numbers too - but the only honest claim is the one on this line.

Each check returns a HUMAN score from 0 to 100. Higher is better.

Usage
  python3 detect.py draft.txt
  pbpaste | python3 detect.py -
  python3 detect.py draft.txt --json
  python3 detect.py before.txt after.txt      # compare two drafts
  python3 detect.py brouillon.txt --langue fr # French (detected by default)

In French the panel uses the "fr" block of slop.json, counts spoken markers
(ça, on, t'as, y a...) instead of English contractions, French pronouns, and
does not count French typography (’, …, no-break spaces) as a fingerprint.
"""

import argparse
import json
import os
import re
import statistics
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
LEX = os.path.join(HERE, "slop.json")

SENT_RE = re.compile(r"[^.!?\n]+[.!?]*")
WORD_RE = re.compile(r"[A-Za-z']+")
CONTRACTIONS = re.compile(r"\b\w+'(?:s|t|re|ve|ll|d|m)\b", re.IGNORECASE)
PRONOUNS = re.compile(r"\b(i|me|my|mine|we|us|our|you|your)\b", re.IGNORECASE)
NUMBERS = re.compile(r"\b\d[\d,.]*%?\b|\$\d")
PROPER = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-z]{2,}\b", re.MULTILINE)

# French counterparts. Elision ("c'est", "l'ours") is not a sign of a human
# in French, it is the grammar, so VOICE counts spoken markers instead.
FR_WORD_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")
FR_SPOKEN = re.compile(r"\b(?:ça|on|t['’]as|t['’]es|y['’]?\s?a|bref|bon|hein|genre|truc)\b",
                       re.IGNORECASE)
FR_PRONOUNS = re.compile(r"\b(?:je|j['’]|me|m['’]|moi|mon|ma|mes|nous|notre|nos|tu|t['’]|te|toi|"
                         r"ton|ta|tes|vous|votre|vos|on)(?=\W|$)", re.IGNORECASE)
FR_PROPER = re.compile(r"(?<![.!?…«—]\s)(?<![«—])(?<!^)\b[A-ZÀ-Ý][a-zà-ÿ]{2,}\b", re.MULTILINE)
# Stories and captions in French spell small numbers out. They are as
# checkable as digits.
FR_NUMBER_WORDS = re.compile(r"\b(?:deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze|"
                             r"quinze|vingt|trente|quarante|cinquante|soixante|cent|cents|mille|"
                             r"million|millions|douzaine|deuxième|troisième|dixième|centième|"
                             r"moitié|double|triple)\b", re.IGNORECASE)
FR_TYPO_NBSP = re.compile(r"[\u00a0\u202f](?=[;:!?»%€])|(?<=«)[\u00a0\u202f]"
                          r"|(?<=\d)[\u00a0\u202f](?=\d)")
FR_WORDS = re.compile(r"\b(?:le|la|les|des|une|est|et|que|qui|pas|pour|dans|ce|cette|avec|"
                      r"sur|je|tu|nous|vous|il|elle|ça|du|au|aux|mais)\b|\b(?:[cdjlmnst]|qu)['’]",
                      re.IGNORECASE)
EN_WORDS = re.compile(r"\b(?:the|and|is|are|to|of|you|your|that|it|this|with|for|was|"
                      r"i|my|we|but|not)\b", re.IGNORECASE)


def detect_language(text):
    """'fr' when French function words outnumber English ones."""
    return "fr" if len(FR_WORDS.findall(text)) > len(EN_WORDS.findall(text)) else "en"


def for_language(lex, lang):
    """The lexicon a given language should be checked against."""
    if lang != "fr" or "fr" not in lex:
        return lex
    fr = lex["fr"]
    shared = [s for s in lex["structures"] if s["id"] in fr.get("reprend", [])]
    return dict(lex, words=fr["words"], phrases=fr["phrases"],
                structures=fr["structures"] + shared, lang="fr")


def clamp(n):
    return max(0.0, min(100.0, n))


def scale(value, human, machine):
    """Map value onto 0-100 where `human` -> 100 and `machine` -> 0."""
    if human == machine:
        return 50.0
    return clamp((value - machine) / (human - machine) * 100)


def sentences(text):
    return [s.strip() for s in SENT_RE.findall(text) if len(s.split()) > 2]


def words(text, lang="en"):
    return (FR_WORD_RE if lang == "fr" else WORD_RE).findall(text)


def check_burstiness(text):
    """Humans vary sentence length hard. Models write even."""
    lens = [len(s.split()) for s in sentences(text)]
    if len(lens) < 4:
        return 50.0, "too short to judge"
    mean = statistics.mean(lens)
    cv = statistics.pstdev(lens) / mean if mean else 0
    score = scale(cv, human=0.70, machine=0.22)
    return score, f"variation {cv:.2f} across {len(lens)} sentences (want 0.55+)"


def check_specificity(text, lang="en"):
    """Numbers, names and concrete nouns. Slop is abstract."""
    w = words(text, lang)
    if len(w) < 25:
        return 50.0, "too short to judge"
    per100 = 100 / len(w)
    proper = FR_PROPER if lang == "fr" else PROPER
    hits = len(NUMBERS.findall(text)) + len(set(proper.findall(text)))
    if lang == "fr":
        hits += len(FR_NUMBER_WORDS.findall(text))
    density = hits * per100
    score = scale(density, human=6.0, machine=0.5)
    return score, f"{hits} concrete markers, {density:.1f} per 100 words (want 4+)"


def check_slop(text, lex):
    """Stock vocabulary density against the lexicon."""
    w = words(text, lex.get("lang", "en"))
    if not w:
        return 50.0, "empty"
    hits, found = 0, []
    for entry in lex["words"] + lex["phrases"]:
        pattern = re.compile(r"\b" + re.escape(entry["find"]).replace(r"\ ", r"\s+") + r"\b",
                             re.IGNORECASE)
        n = len(pattern.findall(text))
        if n:
            hits += n
            found.append(entry["find"])
    density = hits * 100 / len(w)
    score = scale(density, human=0.0, machine=4.0)
    detail = f"{hits} stock terms, {density:.1f} per 100 words"
    if found:
        detail += " (" + ", ".join(sorted(found)[:4]) + (", ..." if len(found) > 4 else "") + ")"
    return score, detail


def check_fingerprint(text, lang="en"):
    """Characters a phone keyboard does not produce."""
    invisible = sum(1 for c in text if unicodedata.category(c) == "Cf")
    em = text.count("—")
    curly = sum(text.count(c) for c in "‘’“”")
    ellip = text.count("…")
    nbsp = sum(text.count(c) for c in "   ")
    if lang == "fr":
        # French typography: ’ and … come from the keyboard, a no-break space
        # belongs before ; : ! ? », after « and inside 1 800, and a dash opens
        # a line of dialogue.
        em -= len(re.findall(r"(?m)^[ \t]*—", text))
        curly = sum(text.count(c) for c in "‘“”")
        ellip = 0
        nbsp -= len(FR_TYPO_NBSP.findall(text))
    total = invisible * 4 + em * 2 + curly + ellip + nbsp
    per1k = total * 1000 / max(len(text), 1)
    score = scale(per1k, human=0.0, machine=12.0)
    detail = (f"{invisible} invisible, {em} em dash, {curly} curly quote, "
              f"{ellip} ellipsis, {nbsp} hard space")
    return score, detail


def check_voice(text, lex):
    """Contractions, person, and the shapes models default to."""
    fr = lex.get("lang") == "fr"
    w = words(text, lex.get("lang", "en"))
    if len(w) < 25:
        return 50.0, "too short to judge"
    per100 = 100 / len(w)
    contractions = len((FR_SPOKEN if fr else CONTRACTIONS).findall(text)) * per100
    person = len((FR_PRONOUNS if fr else PRONOUNS).findall(text)) * per100
    tells = 0
    names = []
    for s in lex["structures"]:
        try:
            n = len(re.compile(s["regex"], re.MULTILINE).findall(text))
        except re.error:
            continue
        if n:
            tells += n
            names.append(s["id"])
    bullets = [len(b.split()) for b in re.findall(r"(?m)^\s*[-*•]\s+(.+)$", text)]
    uniform = (len(bullets) >= 3 and statistics.pstdev(bullets) < 1.6)
    score = (scale(contractions, human=3.0, machine=0.0) * 0.35
             + scale(person, human=8.0, machine=1.0) * 0.35
             + clamp(100 - tells * 22) * 0.30)
    if uniform:
        score -= 12
        names.append("uniform-bullets")
    detail = (f"{contractions:.1f} {'spoken markers' if fr else 'contractions'}, "
              f"{person:.1f} personal pronouns "
              f"per 100 words, {tells} structural tell(s)")
    if names:
        detail += " [" + ", ".join(names[:4]) + "]"
    return clamp(score), detail


CHECKS = ["BURSTINESS", "SPECIFICITY", "SLOP DENSITY", "FINGERPRINT", "VOICE"]


def run(text, lex, lang="auto"):
    if lang == "auto":
        lang = detect_language(text)
    lex = for_language(lex, lang)
    results = {}
    results["BURSTINESS"] = check_burstiness(text)
    results["SPECIFICITY"] = check_specificity(text, lang)
    results["SLOP DENSITY"] = check_slop(text, lex)
    results["FINGERPRINT"] = check_fingerprint(text, lang)
    results["VOICE"] = check_voice(text, lex)
    scores = [results[c][0] for c in CHECKS]
    # The weakest check drags the verdict: a detector only needs one signal.
    overall = statistics.mean(scores) * 0.6 + min(scores) * 0.4
    verdict = "PASS" if overall >= 70 and min(scores) >= 55 else (
        "REVIEW" if overall >= 50 else "FLAGGED")
    return results, overall, verdict


def bar(score, width=24):
    filled = round(score / 100 * width)
    return "#" * filled + "." * (width - filled)


def render(results, overall, verdict, label=None, out=sys.stdout):
    title = "AI DETECTION PANEL" + (f"  -  {label}" if label else "")
    print("\n" + title, file=out)
    print("=" * max(len(title), 62), file=out)
    for name in CHECKS:
        score, detail = results[name]
        print(f"  {name:<13} {bar(score)} {score:5.1f}", file=out)
        print(f"  {'':<13} {detail}", file=out)
    print("-" * 62, file=out)
    print(f"  {'HUMAN SCORE':<13} {bar(overall)} {overall:5.1f}   {verdict}", file=out)
    if verdict != "PASS":
        weakest = min(CHECKS, key=lambda c: results[c][0])
        print(f"\n  Weakest signal: {weakest}. Fix that first.", file=out)
    print("", file=out)


def main():
    ap = argparse.ArgumentParser(description="Score how machine-written a draft looks.")
    ap.add_argument("input", nargs="?", default="-", help="file, or - for stdin")
    ap.add_argument("compare", nargs="?", help="second file, to show before/after")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--lexicon", default=LEX)
    ap.add_argument("--langue", choices=["auto", "en", "fr"], default="auto",
                    help="language of the draft (default: detected)")
    args = ap.parse_args()

    lex = json.load(open(args.lexicon, encoding="utf-8"))
    read = lambda p: sys.stdin.read() if p == "-" else open(p, encoding="utf-8").read()

    targets = [(args.input, read(args.input))]
    if args.compare:
        targets.append((args.compare, read(args.compare)))

    payload = []
    for name, text in targets:
        results, overall, verdict = run(text, lex, args.langue)
        payload.append({
            "source": name,
            "checks": {k: {"score": round(v[0], 1), "detail": v[1]} for k, v in results.items()},
            "human_score": round(overall, 1),
            "verdict": verdict,
        })

    if args.json:
        print(json.dumps(payload if args.compare else payload[0], indent=2))
        return

    for (name, text), p in zip(targets, payload):
        results, overall, verdict = run(text, lex, args.langue)
        render(results, overall, verdict, label=os.path.basename(name) if args.compare else None)
    if args.compare:
        a, b = payload
        delta = b["human_score"] - a["human_score"]
        print(f"  {a['human_score']:.1f} {a['verdict']}  ->  "
              f"{b['human_score']:.1f} {b['verdict']}   ({delta:+.1f})\n")

    sys.exit(0 if payload[-1]["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
