#!/usr/bin/env python3
"""
hookscore.py - score the first line of a Reel on the five things strong hooks
have in common, and rank a batch of them against each other.

What this is:  five local heuristics, computed on your machine from the text
alone. They measure properties that hooks which hold attention tend to share -
a length you can say in under three seconds, a concrete marker, something at stake,
the payload at the front rather than the back, and a viewer to aim it at.

What this is NOT:  a view predictor. It was tested against 74 real short-form
hooks, transcribed from the first three seconds of the top eight and bottom
eight performers on five channels. Separating a real hook from a deliberately
bad one it does well: AUC 0.83, and 9 of 10 written-to-be-bad hooks scored
below the real median. Separating a good creator's hits from that same
creator's misses it barely does at all: AUC 0.56, where 0.50 is a coin flip.

So use it for what it measured well. It catches greetings, preambles, hooks
with nothing concrete in them and hooks that take five seconds to say. It will
not tell you which of two decent hooks will travel, and nothing that reads text
can, because that is decided by your face, your edit, your audio and who
Instagram shows it to. Trust the retention graph over this script.

Each check returns 0 to 100. Higher is better.

Usage
  python3 hookscore.py hooks.txt              # one hook per line, ranked
  python3 hookscore.py --hook "I lost $18,000 on one missing contract."
  pbpaste | python3 hookscore.py -
  python3 hookscore.py hooks.txt --json
  python3 hookscore.py --hook "1 800 soirs : c'est ce qui t'attend." --langue fr

French hooks (detected automatically) are scored with French word lists:
negation and stakes (jamais, personne, avant, sans...), tu/vous, French
greetings and preambles, numbers written as words, and a length window two
words wider, because the same line takes more words in French. The French
lists were not calibrated on real hooks the way the English ones were.
"""

import argparse
import json
import re
import statistics
import sys

WORD_RE = re.compile(r"[A-Za-z0-9$%'’-]+")
NUMBER_RE = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?"                       # money, whole
    r"|\b\d[\d,]*(?:\.\d+)?\s?"                      # a figure, with or
    r"(?:%|k\b|x\b|hrs?\b|hours?\b|mins?\b|minutes?\b"  # without a unit
    r"|days?\b|weeks?\b|months?\b|years?\b)?",
    re.IGNORECASE)
PROPER_RE = re.compile(r"(?<!^)\b[A-Z][a-z]{2,}\b")
HASHTAG_RE = re.compile(r"(?:^|\s)#\w+")
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF☀-➿]")

# Spoken hooks say their numbers out loud. "Zero dollars" and "twenty grand"
# are as concrete as "$0" and "$20,000", and counting only digits missed them.
# "one" and "first" are deliberately absent: they are filler far more often
# than they are a quantity.
SPOKEN_NUMBERS = {
    "zero", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "fifteen", "twenty", "thirty", "forty", "fifty",
    "sixty", "seventy", "eighty", "ninety", "hundred", "thousand", "million",
    "billion", "dozen", "half", "twice", "triple",
}
MONEY_WORDS = {
    "dollars", "dollar", "bucks", "grand", "percent", "cents",
    "millionaire", "billionaire", "revenue", "profit", "salary", "rent",
}

# Words that put something on the line. A hook with none of these is a
# statement; a hook with one is a reason to keep watching.
STAKES = {
    "stop", "never", "wrong", "mistake", "mistakes", "lost", "lose", "losing",
    "cost", "costs", "broke", "broken", "failed", "failure", "fail", "nobody",
    "no", "not", "don't", "dont", "doesn't", "didn't", "can't", "won't",
    "quit", "quitting", "fired", "deleted", "delete", "killed", "kills", "kill",
    "replaced", "replaces", "cut", "beat", "free", "paid", "charged", "hired",
    "saved", "first",
    "banned", "illegal", "worst", "hate", "hated", "wasted", "waste", "scam",
    "lie", "lied", "lying", "truth", "secret", "hidden", "stole", "stolen",
    "before", "until", "instead", "but", "except", "unless", "problem",
    "risk", "danger", "warning", "regret", "wish", "should", "shouldn't",
    "still", "already", "only", "without", "versus", "vs", "actually",
}

# Openers that spend the first second saying nothing.
WEAK_OPENERS = [
    "so", "ok", "okay", "hey", "hi", "hello", "guys", "yo", "alright",
    "welcome", "today", "basically", "honestly", "look", "listen", "um",
    "just", "let", "lets", "let's", "i wanted", "i want", "one of",
    "have you", "did you", "do you", "are you", "in this", "in today",
    "the thing", "a lot", "there is", "there are", "this is", "it is",
    "as a", "when it", "if you've", "you know",
]

# Imperatives that earn the front position.
IMPERATIVES = {
    "stop", "steal", "copy", "delete", "try", "watch", "read", "save",
    "use", "build", "make", "write", "send", "take", "start", "quit",
    "never", "always", "don't", "dont", "do", "put", "run", "check",
}

DEALBREAKERS = [
    (re.compile(r"(?i)^\s*(?:stop scrolling|don'?t scroll)"),
     "Opens with \"stop scrolling\". Asking for attention proves you have not earned it."),
    (re.compile(r"(?i)\b(?:in (?:this|today'?s) (?:video|reel)|i'?m going to show you|i'?ll show you how)\b"),
     "Video preamble. Delete it and open on the payoff."),
    (re.compile(r"(?i)^\s*(?:hey |hi |what'?s up |welcome )"),
     "Greeting. Nobody came to the feed to be greeted."),
    (HASHTAG_RE,
     "Hashtag in the hook. Hashtags belong at the bottom of the caption, if anywhere."),
    (EMOJI_RE,
     "Emoji in the hook. On-screen text at hook size has room for words or for an emoji, not both."),
]


FR_WORD_RE = re.compile(r"[\w$%€'’-]+")
FR_ELISION = re.compile(r"^(?:[cdjlmnst]|qu|jusqu|lorsqu|puisqu)['’]", re.IGNORECASE)
FR_NUMBER_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s?"
    r"(?:%|€|k\b|x\b|h\b|heures?\b|min\b|minutes?\b|jours?\b|semaines?\b|mois\b"
    r"|ans?\b|années?\b|soirs?\b|nuits?\b|euros?\b)?",
    re.IGNORECASE)
FR_PROPER_RE = re.compile(r"(?<!^)\b[A-ZÀ-Ý][a-zà-ÿ]{2,}\b")
FR_SPOKEN_NUMBERS = {
    "zéro", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix",
    "onze", "douze", "quinze", "vingt", "trente", "quarante", "cinquante", "soixante",
    "cent", "cents", "mille", "million", "millions", "milliard", "douzaine", "moitié",
    "double", "triple",
}
FR_MONEY_WORDS = {
    "euros", "euro", "balles", "salaire", "loyer", "bénéfice", "chiffre", "prix",
    "millionnaire", "gratuit", "gratuite",
}
FR_STAKES = {
    "arrête", "arrêtez", "jamais", "personne", "rien", "pas", "plus", "erreur",
    "erreurs", "faux", "perdu", "perdre", "perds", "coûte", "coûté", "raté", "échec",
    "viré", "supprimé", "gratuit", "payé", "sauvé", "premier", "première", "interdit",
    "pire", "déteste", "gaspillé", "arnaque", "mensonge", "menti", "vérité", "secret",
    "caché", "volé", "avant", "jusqu", "sans", "sauf", "mais", "problème", "risque",
    "danger", "attention", "regret", "regrette", "dois", "doit", "devrais", "faut",
    "encore", "déjà", "seulement", "enfin", "contre", "trop", "tard", "dernier",
    "dernière", "oublie", "oublié",
}
FR_WEAK_OPENERS = [
    "alors", "donc", "ok", "bon", "salut", "coucou", "bonjour", "hello", "les amis",
    "bienvenue", "aujourd'hui", "aujourd’hui", "en fait", "honnêtement", "écoute",
    "écoutez", "euh", "juste", "je voulais", "je veux", "l'une des", "l’une des",
    "un des", "une des", "est-ce que", "vous avez", "tu as", "dans cette", "dans ce",
    "il y a", "c'est", "c’est", "voici", "quand on", "vous savez", "tu sais",
]
FR_IMPERATIVES = {
    "arrête", "arrêtez", "essaie", "essayez", "copie", "copiez", "vole", "volez",
    "supprime", "regarde", "regardez", "lis", "lisez", "garde", "gardez", "enregistre",
    "utilise", "utilisez", "fais", "faites", "écris", "écrivez", "envoie", "prends",
    "prenez", "commence", "commencez", "ne", "n", "jamais", "toujours", "mets",
    "lance", "teste", "vérifie", "imagine", "imaginez", "oublie", "oubliez",
}
FR_DEALBREAKERS = [
    (re.compile(r"(?i)^\s*(?:arrête[sz]? de scroller|ne scrolle pas|stop au scroll)"),
     "Opens with \"arrête de scroller\". Asking for attention proves you have not earned it."),
    (re.compile(r"(?i)\b(?:dans (?:cette|la) vidéo|dans ce reel|je vais (?:te|vous) (?:montrer|expliquer))\b"),
     "Video preamble. Delete it and open on the payoff."),
    (re.compile(r"(?i)^\s*(?:salut|coucou|bonjour|hello|bienvenue)\b"),
     "Greeting. Nobody came to the feed to be greeted."),
    (HASHTAG_RE,
     "Hashtag in the hook. Hashtags belong at the bottom of the caption, if anywhere."),
    (EMOJI_RE,
     "Emoji in the hook. On-screen text at hook size has room for words or for an emoji, not both."),
]
FR_WORDS = re.compile(r"\b(?:le|la|les|des|une|est|et|que|qui|pas|pour|dans|ce|cette|avec|"
                      r"sur|je|tu|nous|vous|il|elle|ça|du|au|aux|mais|ton|ta|tes)\b"
                      r"|\b(?:[cdjlmnst]|qu)['’]", re.IGNORECASE)
EN_WORDS = re.compile(r"\b(?:the|and|is|are|to|of|you|your|that|it|this|with|for|was|"
                      r"i|my|we|but|not)\b", re.IGNORECASE)

EN = {
    "word_re": WORD_RE, "number_re": NUMBER_RE, "proper_re": PROPER_RE,
    "spoken": SPOKEN_NUMBERS, "money": MONEY_WORDS, "stakes": STAKES,
    "weak": WEAK_OPENERS, "imperatives": IMPERATIVES, "dealbreakers": DEALBREAKERS,
    "you": r"\b(you|your|you're|youre|yourself)\b", "me": r"\b(i|my|me|we|our)\b",
    "price": r"\$\s?\d", "max_words": 12, "max_chars": 60,
}
FR = {
    "word_re": FR_WORD_RE, "number_re": FR_NUMBER_RE, "proper_re": FR_PROPER_RE,
    "spoken": FR_SPOKEN_NUMBERS, "money": FR_MONEY_WORDS, "stakes": FR_STAKES,
    "weak": FR_WEAK_OPENERS, "imperatives": FR_IMPERATIVES, "dealbreakers": FR_DEALBREAKERS,
    "you": r"\b(?:tu|te|toi|ton|ta|tes|vous|votre|vos)\b|\bt['’]",
    "me": r"\b(?:je|moi|mon|ma|mes|nous|notre|nos|on)\b|\b[jm]['’]",
    "price": r"\d\s?€|€\s?\d", "max_words": 14, "max_chars": 70,
}


def detect_language(text):
    """'fr' when French function words outnumber English ones."""
    return "fr" if len(FR_WORDS.findall(text)) > len(EN_WORDS.findall(text)) else "en"


def clamp(n):
    return max(0.0, min(100.0, n))


def words(text, L=EN):
    # "$18,000" is one word when it is spoken, so it is one word here too.
    # So is "1 800" in French, with a plain or a no-break space.
    if L is FR:
        return L["word_re"].findall(re.sub(r"(?<=\d)[ \u00a0\u202f](?=\d{3}\b)", "", text))
    return WORD_RE.findall(re.sub(r"(?<=\d),(?=\d)", "", text))


def bare(token, L=EN):
    """Lower case, quotes off, and in French the elided article too: l'ours -> ours."""
    token = token.lower().strip("'’")
    return FR_ELISION.sub("", token) if L is FR else token


def check_length(text, L=EN):
    """A hook has to land before the thumb moves. Roughly two seconds."""
    w = words(text, L)
    n = len(w)
    secs = n / 2.75                      # ~165 words per minute, spoken
    chars = len(text.strip())
    top = L["max_words"]
    if 5 <= n <= top:
        score = 100.0
    elif n < 5:
        score = clamp(100 - (5 - n) * 20)
    else:
        score = clamp(100 - (n - top) * 11)
    if chars > L["max_chars"]:           # two lines of big on-screen text
        score -= 12
    return clamp(score), f"{n} words, {chars} chars, ~{secs:.1f}s spoken (want 5-{top} words)"


def check_specificity(text, L=EN):
    """One concrete thing beats three abstract ones."""
    nums = [n.strip() for n in L["number_re"].findall(text) if n.strip()]
    propers = set(L["proper_re"].findall(text))
    low = [bare(w, L) for w in words(text, L)]
    spoken = [w for w in low if w in L["spoken"] or w in L["money"]]
    hits = len(nums) + len(propers) + len(spoken)
    score = 15.0 if hits == 0 else clamp(45 + hits * 30)
    found = ", ".join(nums[:2] + sorted(propers)[:2] + spoken[:2])
    return score, (f"{hits} concrete marker(s)" + (f": {found}" if found else
                   " - no number, no name, nothing checkable"))


def check_stakes(text, L=EN):
    """Tension, cost, negation. Something the viewer might lose."""
    w = [bare(x, L) for x in words(text, L)]
    hits = [x for x in w if x in L["stakes"]]
    markers = sorted(set(hits))
    if re.search(L["price"], text):
        markers.append("a price")
    n = len(markers)
    score = {0: 20.0, 1: 70.0}.get(n, 100.0)
    detail = f"{n} tension marker(s)" + (f": {', '.join(markers[:4])}" if markers else
                                         " - nothing is at stake in this line")
    return clamp(score), detail


def check_frontload(text, L=EN):
    """The interesting word cannot be in position nine."""
    w = words(text, L)
    if not w:
        return 0.0, "empty"
    raw = [x.lower().strip("'’") for x in w]
    low = [bare(x, L) for x in w]
    opener = " ".join(raw[:2])
    penalty = 0
    hit_opener = None
    for weak in L["weak"]:
        if opener.startswith(weak) or raw[0] == weak:
            penalty, hit_opener = 30, weak
            break
    payload = None
    for i, token in enumerate(low):
        if (token in L["stakes"] or token in L["spoken"] or token in L["money"]
                or L["number_re"].match(w[i]) or (i and L["proper_re"].match(w[i]))):
            payload = i
            break
    if payload is None:
        base = 30.0
        where = "no payload word anywhere in the line"
    elif payload <= 3:
        base = 100.0
        where = f"payload at word {payload + 1}"
    elif payload <= 6:
        base = 70.0
        where = f"payload at word {payload + 1}, could move forward"
    else:
        base = 40.0
        where = f"payload at word {payload + 1}, too late"
    detail = where + (f"; weak opener \"{hit_opener}\"" if hit_opener else "")
    return clamp(base - penalty), detail


def check_address(text, L=EN):
    """Aimed at one viewer, or floating in the air."""
    low = text.lower()
    w = [bare(x, L) for x in words(text, L)]
    if re.search(L["you"], low):
        return 100.0, "speaks to the viewer"
    if w and w[0] in L["imperatives"]:
        return 90.0, f"imperative opener (\"{w[0]}\")"
    if re.search(L["me"], low):
        return 70.0, "first person, no viewer named"
    return 35.0, "third person, nobody in the room"


CHECKS = ["LENGTH", "SPECIFICITY", "STAKES", "FRONTLOAD", "ADDRESS"]


def run(text, lang="auto"):
    if lang == "auto":
        lang = detect_language(text)
    L = FR if lang == "fr" else EN
    results = {
        "LENGTH": check_length(text, L),
        "SPECIFICITY": check_specificity(text, L),
        "STAKES": check_stakes(text, L),
        "FRONTLOAD": check_frontload(text, L),
        "ADDRESS": check_address(text, L),
    }
    flags = [msg for pattern, msg in L["dealbreakers"] if pattern.search(text)]
    scores = [results[c][0] for c in CHECKS]
    # The weakest property caps the hook, same logic as detect.py: one bad
    # property is enough for the thumb to keep moving.
    overall = statistics.mean(scores) * 0.6 + min(scores) * 0.4 - len(flags) * 15
    overall = clamp(overall)
    verdict = "STRONG" if overall >= 70 and min(scores) >= 55 and not flags else (
        "OK" if overall >= 50 else "WEAK")
    return results, overall, verdict, flags


def bar(score, width=24):
    filled = round(score / 100 * width)
    return "#" * filled + "." * (width - filled)


def render_one(text, results, overall, verdict, flags, out=sys.stdout):
    print("\nHOOK SCORE", file=out)
    print("=" * 62, file=out)
    print(f"  \"{text.strip()}\"\n", file=out)
    for name in CHECKS:
        score, detail = results[name]
        print(f"  {name:<13} {bar(score)} {score:5.1f}", file=out)
        print(f"  {'':<13} {detail}", file=out)
    print("-" * 62, file=out)
    print(f"  {'HOOK SCORE':<13} {bar(overall)} {overall:5.1f}   {verdict}", file=out)
    for f in flags:
        print(f"\n  DEALBREAKER  {f}", file=out)
    if verdict != "STRONG":
        weakest = min(CHECKS, key=lambda c: results[c][0])
        print(f"\n  Weakest property: {weakest}. Fix that one and re-run.", file=out)
    print("", file=out)


def render_table(rows, out=sys.stdout):
    print("\nHOOK RANKING\n" + "=" * 78, file=out)
    for i, r in enumerate(rows, 1):
        mark = "->" if i == 1 else "  "
        hook = r["hook"] if len(r["hook"]) <= 62 else r["hook"][:59] + "..."
        print(f"{mark} {r['score']:5.1f} {r['verdict']:<7} {hook}", file=out)
        print(f"        weakest: {r['weakest']} ({r['checks'][r['weakest']]['score']:.0f})", file=out)
        for f in r["flags"]:
            print(f"        dealbreaker: {f}", file=out)
    print("\nShoot the top one. If the top one is under 50, none of these are the hook.\n",
          file=out)


def main():
    ap = argparse.ArgumentParser(description="Score a Reel hook on five properties.")
    ap.add_argument("input", nargs="?", default="-", help="file with one hook per line, or -")
    ap.add_argument("--hook", help="score a single hook given on the command line")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--langue", choices=["auto", "en", "fr"], default="auto",
                    help="language of the hooks (default: detected per hook)")
    args = ap.parse_args()

    if args.hook:
        lines = [args.hook]
    else:
        raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
    if not lines:
        print("nothing to score", file=sys.stderr)
        sys.exit(2)

    payload = []
    for line in lines:
        results, overall, verdict, flags = run(line, args.langue)
        payload.append({
            "hook": line,
            "checks": {k: {"score": round(v[0], 1), "detail": v[1]} for k, v in results.items()},
            "weakest": min(CHECKS, key=lambda c: results[c][0]),
            "flags": flags,
            "score": round(overall, 1),
            "verdict": verdict,
        })

    if args.json:
        print(json.dumps(payload if len(payload) > 1 else payload[0], indent=2, ensure_ascii=False))
        return

    if len(payload) == 1:
        results, overall, verdict, flags = run(lines[0], args.langue)
        render_one(lines[0], results, overall, verdict, flags)
    else:
        render_table(sorted(payload, key=lambda r: -r["score"]))

    sys.exit(0 if max(p["score"] for p in payload) >= 70 else 1)


if __name__ == "__main__":
    main()
