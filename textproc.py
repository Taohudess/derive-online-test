"""Tokenising and light stemming shared by intent, retrieval and support checks."""
import re

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "of", "to", "in", "on", "at", "by",
    "for", "from", "with", "about", "as", "into", "is", "are", "was", "were", "be",
    "been", "am", "do", "does", "did", "can", "could", "will", "would", "should",
    "may", "might", "must", "i", "me", "my", "you", "your", "we", "our", "it", "its",
    "this", "that", "these", "those", "there", "what", "which", "who", "how", "why",
    "when", "where", "have", "has", "had", "get", "any", "all", "so", "not", "no",
    "they", "their", "them", "he", "she", "his", "her", "us", "please",
}

_SUFFIXES = ("ations", "ation", "ings", "ing", "ures", "ure", "ied", "ies",
             "ed", "es", "er", "al", "s")


def stem(word):
    """Crude suffix stripping so closing/closure/closed all map to 'clos'."""
    for suf in _SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            if suf == "s" and word.endswith("ss"):
                break
            word = word[: -len(suf)]
            break
    if word.endswith("e") and len(word) > 3:
        word = word[:-1]
    return word


def words(text):
    """Lowercase alphanumeric words, no filtering."""
    return re.findall(r"[a-z0-9]+", text.lower())


_HOW_QUANTITY = re.compile(r"\bhow\s+(long|much|many|often|soon|far)\b", re.I)


def tokens(text):
    """Content tokens: stopwords removed, stemmed.

    "how long / how much / ..." is question form, not topic, so the quantity
    word is dropped (otherwise "long" matches "longer" in unrelated articles).
    """
    text = _HOW_QUANTITY.sub("how", text)
    return [stem(w) for w in words(text) if w not in STOPWORDS]


def numbers(text):
    return set(re.findall(r"\d+", text))


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
