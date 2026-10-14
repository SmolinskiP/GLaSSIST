"""Build the text of positive and negative training utterances for a wake word.

Negatives matter as much as positives: they teach the model what is NOT the word. Two rules
learned the hard way:
  * a negative must never contain the wake word itself (it would contradict the positives);
  * near-twins of the word (differing by one letter) are not useful negatives, they make
    training noisy. Words that merely look/sound similar are.
"""
import difflib
import random
import unicodedata


def normalize(text):
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    return ''.join(c for c in text.lower() if c.isalnum() or c == ' ').strip()


def similarity(a, b):
    return difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def _shared_suffix(a, b):
    a, b, n = normalize(a), normalize(b), 0
    while n < min(len(a), len(b)) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n


def contains_word(text, word):
    return normalize(word) in normalize(text)


def pick_confusables(word, candidates, limit=40, low=0.45, high=0.85):
    """Words that look similar to `word` but are not near-twins. Best matches first."""
    target = normalize(word)
    scored = []
    for cand in candidates:
        c = normalize(cand)
        if not c or c == target or target in c or c in target and len(c) >= len(target) - 1:
            continue
        ratio = similarity(word, cand)
        suffix = _shared_suffix(word, cand)
        score = ratio + (0.15 if suffix >= 3 else 0)
        if low <= ratio < high or (suffix >= 3 and ratio < high):
            scored.append((score, cand))
    scored.sort(key=lambda t: -t[0])
    seen, out = set(), []
    for _, cand in scored:
        if normalize(cand) not in seen:
            seen.add(normalize(cand))
            out.append(cand)
        if len(out) >= limit:
            break
    return out


def fragments(word, min_len=3):
    """The first and second half of the word spoken alone: classic false-trigger sources."""
    w = word.strip()
    if len(w) < 2 * min_len:
        return []
    mid = len(w) // 2
    return [w[:mid], w[mid:]]


def positive_phrases(word, prefixes):
    base = [word, word.lower(), f'{word}!', f'{word}?', f'{word}.']
    base += [f'{p} {word}' for p in prefixes]
    base += [f'{p}, {word}' for p in prefixes[:2]]
    return list(dict.fromkeys(base))


def negative_phrases(word, corpus, seed=11, extra_sentences=240):
    """[(text, weight)]: weight > 1 means 'say this one with more voices' (hard negatives)."""
    rng = random.Random(seed)
    out = []
    conf = pick_confusables(word, corpus['words'])
    carriers = [c for c in corpus['carriers'] if '{w}' in c]
    for w in conf:
        out.append((w, 3))
        out.append((rng.choice(carriers).format(w=w), 2))
    for frag in fragments(word):
        out.append((frag, 3))
    for phrase in corpus['phrases']:
        out.append((phrase, 1))
    verbs, objects = corpus['verbs'], corpus['objects']
    for _ in range(extra_sentences):
        kind = rng.random()
        if kind < 0.4:
            text = f'{rng.choice(verbs)} {rng.choice(objects)}'
        elif kind < 0.7:
            text = f'{rng.choice(verbs)} {rng.choice(objects)} e {rng.choice(verbs)} {rng.choice(objects)}'
        else:
            text = f'{rng.choice(corpus["phrases"])}, {rng.choice(corpus["phrases"])}'
        out.append((text, 1))
    for w in rng.sample(corpus['words'], min(60, len(corpus['words']))):
        out.append((w, 1))
    # drop anything that contains the wake word (including accidental carrier phrases)
    out = [(t, wt) for t, wt in out if not contains_word(t, word)]
    # de-duplicate, keep the heaviest weight
    best = {}
    for t, wt in out:
        best[t] = max(wt, best.get(t, 0))
    return sorted(best.items())
