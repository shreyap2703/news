"""Text clean-up, and an extractive summarizer that combines several outlets' reports of the same story."""

import html
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Optional

SUMMARY_MIN_WORDS = 8
# Summaries keep adding sentences until they reach SUMMARY_TARGET_WORDS, and never pass SUMMARY_MAX_WORDS.
SUMMARY_TARGET_WORDS = 100
SUMMARY_MAX_WORDS = 120
SUMMARY_MAX_SENTENCES = 8
# Longer sentences are usually run-ons or lists, which read badly out of context.
MAX_SENTENCE_WORDS = 45
# Weights of the two signals that rank sentences for a multi-source summary: support from other outlets, and
# relevance to the story's headlines. Later sentences of an article and very short ones count for somewhat less.
AGREEMENT_WEIGHT = 0.5
TOPIC_WEIGHT = 0.5
POSITION_DECAY = 0.15
FULL_SENTENCE_WORDS = 18
# A sentence whose key terms the summary already covers to this share repeats it; smaller shares lower its rank.
# Each extra sentence must also bring this many key terms that the summary does not mention yet.
REDUNDANCY_LIMIT = 0.4
REDUNDANCY_PENALTY = 0.5
MIN_NEW_TERMS = 4
# Sentences must share this many key terms with the story's headlines (one, for headlines of three terms or fewer).
MIN_TOPIC_TERMS = 2

_TAG_RE = re.compile(r"<[^>]*>")
_WHITESPACE_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"\w+")
_INVISIBLE_RE = re.compile("[\u00ad\u200b-\u200f\u2060\ufeff]")
# Sentences whose paragraphs were joined without a space, such as "in 2023.Judge William Sullivan said".
_GLUED_SENTENCE_RE = re.compile(r"(?<=[a-z0-9][.!?])(?=[A-Z])|(?<=[a-z0-9][.!?][\"”’])(?=[A-Z])")
# Removed in order from publishers' text so that only the prose about the story is left.
_SUMMARY_NOISE_RES = (
    # Editor's notes such as "(Corrects spelling of name in paragraph 6)", or "(CNN)".
    re.compile(r"^\([^()]{0,120}\)\s*"),
    # Bylines and wire datelines such as "By Jane DoeANTALYA, Turkey, Nov 16 (Reuters) - " or "MUMBAI, India (AP) — ".
    re.compile(r"^.{0,160}?\((?:AP|Reuters|AFP|UPI|Bloomberg|dpa|PTI|IANS|ANI|CNN)\)\s*(?:[-–—]+|:)\s*"),
    # Press release datelines such as "NEW DELHI, Nov. 16, 2026 /PRNewswire/ -- ".
    re.compile(
        r"^.{0,120}?/\s*(?:PR ?Newswire|Business ?Wire|Globe ?Newswire|ACCESSWIRE|EIN ?Presswire)[^/]{0,40}/\s*(?:[-–—]+|:)?\s*",
        re.IGNORECASE,
    ),
    # Labels such as "Synopsis: " or "BREAKING: ".
    re.compile(
        r"^(?:synopsis|summary|highlights?|key takeaways|update[d]?|breaking|exclusive|analysis|explainer|opinion|"
        r"watch|listen|live|photos?|video)\s*:\s*",
        re.IGNORECASE,
    ),
    # Bylines joined to the first sentence, such as "By Jane DoeIndian bonds fell…".
    re.compile(r"^By (?:[A-Z][\w'’.-]* ){0,3}[A-Z][a-z'’.-]+(?=[A-Z][a-z])"),
    # Labels such as "STORY::: ".
    re.compile(r"^[A-Z][A-Z ]{2,20}:{2,}\s*"),
    re.compile(r"^FILE\s*[-–—:]+\s*"),
    re.compile(r"^[-–—:]+\s*"),
    # Photo credits such as "(AP Photo/Vahid Salemi)", and credits that the site cut off.
    re.compile(r"\s*\([^()]*\b(?:Photo|Pool|AP|Reuters|AFP|Getty)\b[^()]*\)$"),
    re.compile(r"\s*\([^()]*$"),
    # Calls to action such as "Read more." or "DW has more."
    re.compile(r"\s*(?:Read more|Learn more|Find out more|Click here[^.!?]*|[A-Z][\w.&-]* has more)[.!…]*$"),
)
# Sentences about the website rather than the story: subscriptions, cookies, credits, and so on.
_JUNK_RE = re.compile(
    r"subscri|newsletter|sign up|log ?in\b|cookie|advertis|all rights reserved|©|copyright|click here|read more|"
    r"follow us|download (?:the|our) app|terms of (?:use|service)|privacy policy|our standards|reporting by|"
    r"editing by|writing by|contributed to this report|(?:image|photo|video|watch|listen|related)\s*:|javascript|"
    r"your browser|per month|free trial|cancel anytime|\bstoryline \d",
    re.IGNORECASE,
)
_COMPLETE_SENTENCE_RE = re.compile(r"[.!?][\"'”’)]*$")
# Initials and initialisms such as "J." or "U.S." do not end a sentence.
_INITIALISM_RE = re.compile(r"(?:[A-Za-z]\.)*[A-Za-z]")
# Abbreviations that are always followed by a name or a date, such as "Sen. Warren" or "Nov. 16".
_TITLES_AND_MONTHS = frozenset(
    {
        "mr", "mrs", "ms", "dr", "prof", "sen", "rep", "gov", "gen", "lt", "col", "sgt", "capt", "rev", "hon", "pres",
        "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    }
)
# Words that end with a period without ending the sentence.
_ABBREVIATIONS = _TITLES_AND_MONTHS | {"st", "jr", "sr", "no", "vs", "inc", "co", "corp", "ltd", "mt", "ft"}
_STOPWORDS = frozenset(
    """
    a about above after again against ahead all also am amid among an and any are around as at be because been
    before being below between both but by can could did do does doing down during each even ever every few for
    from further had has have having he her here hers him his how i if in into is it its just last latest like
    made make many may me might more most much must my new news no nor not now of off on once one only or other
    our out over own per report reports said same says say she should since so some still such than that the
    their them then there these they this those through to too under until up upon us very via was we were what
    when where which while who whom why will with within without would year years you your
    """.split()
)
# A sentence starting with one of these words leans on the sentence before it, e.g. "She said..." or "But...".
_DEPENDENT_STARTS = frozenset(
    """
    he she they it its his her their them this these those that there here but and or also however meanwhile
    still yet so then such both another others which who whose while
    """.split()
)


def clean_text(value: Optional[str]) -> str:
    text = html.unescape(_TAG_RE.sub(" ", value or ""))
    return _WHITESPACE_RE.sub(" ", text).strip()


def normalize(text: str) -> str:
    return " ".join(_WORD_RE.findall(text.lower()))


def clean_passage(text: str) -> str:
    """Turn a publisher's description or paragraph into plain prose, without bylines, datelines, or credits."""
    text = _GLUED_SENTENCE_RE.sub(" ", clean_text(_INVISIBLE_RE.sub("", text).replace("•", " ")))
    for pattern in _SUMMARY_NOISE_RES:
        text = pattern.sub("", text).strip()
    return text


def pick_summary(candidates: Iterable[str], title: str) -> str:
    """Return the first natural, informative description of an article, cleaned up and shortened, or ""."""
    usable = [text for text in (_clean_summary(candidate or "", title) for candidate in candidates) if text]
    # Prefer a sentence or two with some detail over a one-line teaser.
    best = next((text for text in usable if len(text.split()) >= 15), usable[0] if usable else "")
    return _shorten(best) if best else ""


def _clean_summary(text: str, title: str) -> str:
    """Tidy a publisher's description into plain prose about the story, or return "" if it is not usable."""
    text = clean_passage(text)
    # "Headline - Section | Site" is a page title, not a description.
    if " | " in text:
        return ""
    text = _without_headline(text, title)
    if len(text.split()) < SUMMARY_MIN_WORDS or _repeats_title(text, title):
        return ""
    return text


def _without_headline(text: str, title: str) -> str:
    """Drop a copy of the headline from the start of the text, which some sites put in their descriptions."""
    words, title_words = text.split(), title.split()
    if title_words and normalize(" ".join(words[: len(title_words)])) == normalize(title):
        return " ".join(words[len(title_words) :]).lstrip(" -–—:.,")
    return text


def _repeats_title(text: str, title: str) -> bool:
    """True when the text adds at most two words to the headline."""
    return len(set(_WORD_RE.findall(text.lower())) - set(_WORD_RE.findall(title.lower()))) <= 2


def _shorten(text: str) -> str:
    """Keep whole sentences up to SUMMARY_MAX_WORDS, and make the summary end like a sentence."""
    words = text.split()
    cut = False
    if len(words) > SUMMARY_MAX_WORDS:
        end = _last_sentence_end(words, SUMMARY_MAX_WORDS)
        words, cut = (words[:end], False) if end else (words[:SUMMARY_MAX_WORDS], True)
    if words[-1].rstrip(".").lower() in _TITLES_AND_MONTHS:
        # The site cut its description off right after an abbreviation such as "Nov.".
        words, cut = words[:-1], True
    text = " ".join(words)
    if text.endswith("..."):
        text = text[:-3].rstrip() + "…"
    if cut or not text.endswith((".", "!", "?", "…", '"', "”", "’", "'", ")")):
        text = text.rstrip(",;:–—- ")
        # Long descriptions without a full stop were cut off by the publisher's site; short ones just lack it.
        text += "…" if cut or len(text) >= 150 else "."
    return text


def _ends_sentence(word: str, next_word: str) -> bool:
    core = word.rstrip("\"'”’)")
    if not core.endswith((".", "!", "?")) or not (next_word[0].isupper() or next_word[0] in "\"'“‘"):
        return False
    stem = core.rstrip(".!?")
    return not _INITIALISM_RE.fullmatch(stem) and stem.lower() not in _ABBREVIATIONS


def _last_sentence_end(words: list[str], limit: int) -> int:
    """Return how many of the first ``limit`` words make up complete sentences (0 if none)."""
    end = 0
    for index in range(min(limit, len(words) - 1)):
        if _ends_sentence(words[index], words[index + 1]):
            end = index + 1
    return end


def split_sentences(text: str) -> list[str]:
    """Split prose into sentences without breaking at abbreviations such as "Sen." or "U.S."."""
    words = text.split()
    sentences, start = [], 0
    for index in range(len(words) - 1):
        if _ends_sentence(words[index], words[index + 1]):
            sentences.append(" ".join(words[start : index + 1]))
            start = index + 1
    if start < len(words):
        sentences.append(" ".join(words[start:]))
    return sentences


def _stem(word: str) -> str:
    """Strip common endings so that "arrives", "arrived", and "arriving" all become "arriv"."""
    for suffix in ("ing", "ed", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            break
    return word[:-1] if len(word) > 4 and word.endswith("e") else word


def _terms(text: str) -> list[str]:
    return [
        _stem(word)
        for word in _WORD_RE.findall(text.lower())
        if (len(word) > 2 or word.isdigit()) and word not in _STOPWORDS
    ]


def headline_similarity(first: str, second: str) -> tuple[int, float, float]:
    """Compare two headlines' key terms: (shared terms, share of the shorter headline's terms, Jaccard index)."""
    first_terms, second_terms = set(_terms(first)), set(_terms(second))
    if not first_terms or not second_terms:
        return 0, 0.0, 0.0
    shared = len(first_terms & second_terms)
    return shared, shared / min(len(first_terms), len(second_terms)), shared / len(first_terms | second_terms)


def headline_keywords(title: str, limit: int = 5) -> list[str]:
    """Pick search terms for finding other reports of a story: names and places first, then other key words."""
    words: list[str] = []
    for word in re.findall(r"[A-Za-z0-9][\w'’.%-]*", title):
        word = word.rstrip(".-")
        key = word.lower()
        if (len(key) > 2 or key.isdigit()) and key not in _STOPWORDS and all(key != w.lower() for w in words):
            words.append(word)
    names = [word for word in words if word[0].isupper()]
    return (names + [word for word in words if not word[0].isupper()])[:limit]


@dataclass
class _Sentence:
    text: str
    source: int
    position: int
    words: int
    terms: frozenset[str] = frozenset()
    vector: dict[str, float] = field(default_factory=dict)
    # Whether the sentence shares enough key terms with the story's headlines.
    on_topic: bool = False
    score: float = 0.0


def summarize_coverage(
    reports: Sequence[tuple[str, Sequence[str]]],
    max_words: int = SUMMARY_MAX_WORDS,
    max_sentences: int = SUMMARY_MAX_SENTENCES,
) -> str:
    """Write a short extractive summary of a story from several outlets' reports of it, or "" if there is no text.

    ``reports`` holds each outlet's (headline, passages), the story's own report first. Passages are descriptions
    first, then article paragraphs. Sentences rank highly when other outlets report the same facts, when they are
    about the headlines' subject, and when they come early in an article, because news stories lead with the
    essentials. The best sentence that makes sense on its own opens the summary, followed by the best sentences that
    add new facts instead of repeating chosen ones.
    """
    if not reports:
        return ""
    headline = reports[0][0]
    sentences = _candidate_sentences(reports)
    if not sentences:
        return ""

    term_counts = [Counter(_terms(sentence.text)) for sentence in sentences]
    document_frequency = Counter(term for counts in term_counts for term in counts)
    idf = {term: math.log((1 + len(sentences)) / (1 + count)) + 1 for term, count in document_frequency.items()}
    for sentence, counts in zip(sentences, term_counts):
        sentence.terms = frozenset(counts)
        sentence.vector = _unit({term: (1 + math.log(count)) * idf[term] for term, count in counts.items()})
    topic_counts = Counter({term: 2 * count for term, count in Counter(_terms(headline)).items()})
    topic_counts.update(_terms(" ".join(title for title, _ in reports[1:])))
    topic = _unit({term: count * idf.get(term, 1.0) for term, count in topic_counts.items()})
    topic_terms = frozenset(topic_counts)
    # Short headlines such as "Austria Politics" have few terms to share, so one shared term is enough for them.
    min_topic_terms = 1 if len(set(_terms(headline))) <= 3 else MIN_TOPIC_TERMS

    by_source: dict[int, list[_Sentence]] = defaultdict(list)
    for sentence in sentences:
        by_source[sentence.source].append(sentence)
    centroid = _unit(_sum(sentence.vector for sentence in sentences))
    for sentence in sentences:
        agreement = [
            max(_similarity(sentence.vector, other.vector) for other in group)
            for source, group in by_source.items()
            if source != sentence.source
        ]
        support = sum(agreement) / len(agreement) if agreement else _similarity(sentence.vector, centroid)
        relevance = _similarity(sentence.vector, topic)
        sentence.on_topic = len(sentence.terms & topic_terms) >= min_topic_terms
        sentence.score = (
            (AGREEMENT_WEIGHT * support + TOPIC_WEIGHT * relevance)
            / (1 + POSITION_DECAY * sentence.position)
            * min(1.0, math.sqrt(sentence.words / FULL_SENTENCE_WORDS))
        )

    chosen = _select(sentences, max_words, max_sentences)
    return " ".join(sentence.text for sentence in chosen)


def _candidate_sentences(reports: Sequence[tuple[str, Sequence[str]]]) -> list[_Sentence]:
    """Split each outlet's passages into clean, complete, informative sentences, dropping repeats."""
    headline = reports[0][0]
    seen: set[str] = set()
    every_key: list[str] = []
    sentences = []
    for source_index, (title, passages) in enumerate(reports):
        position = 0
        for passage in passages:
            for sentence in split_sentences(clean_passage(passage)):
                # Cleaned again on its own: datelines can also open a passage's later sentences, and some sites run
                # their headline into the first sentence of the article.
                text = _without_headline(clean_passage(sentence), title)
                key = normalize(text)
                every_key.append(key)
                words = len(text.split())
                if (
                    not text
                    or key in seen
                    or not SUMMARY_MIN_WORDS <= words <= MAX_SENTENCE_WORDS
                    or not _COMPLETE_SENTENCE_RE.search(text)
                    or text.endswith("..")
                    # A text cut off by its site right after an abbreviation such as "Nov." only looks complete.
                    or _ends_with_abbreviation(text)
                    or " | " in text
                    or _JUNK_RE.search(text)
                    or _repeats_title(text, headline)
                    or _repeats_title(text, title)
                ):
                    continue
                seen.add(key)
                sentences.append(_Sentence(text, source_index, position, words))
                position += 1
    # Some sites cut descriptions off at a fixed length, sometimes right after a period as in "an estimated 4.".
    # Such a cut-off sentence is the beginning of a fuller one found elsewhere (even one too long to use), so it goes.
    return [
        sentence
        for sentence in sentences
        if not any(other.startswith(normalize(sentence.text) + " ") for other in every_key)
    ]


def _select(sentences: list[_Sentence], max_words: int, max_sentences: int) -> list[_Sentence]:
    """Choose an opening sentence, then sentences that add new facts, and order them for reading."""
    ranked = sorted((s for s in sentences if s.on_topic), key=lambda sentence: sentence.score, reverse=True)
    lead = next((sentence for sentence in ranked if _stands_alone(sentence.text)), None)
    if lead is None:
        return []
    # The lead's own article is about the story even where a sentence does not repeat the headline's terms, so its
    # other sentences may follow once the on-topic ones run out.
    own_article = sorted(
        (s for s in sentences if not s.on_topic and s.source == lead.source),
        key=lambda sentence: sentence.score,
        reverse=True,
    )
    chosen = [lead]
    covered = set(lead.terms)
    used_words = lead.words
    while len(chosen) < max_sentences and used_words < SUMMARY_TARGET_WORDS:
        best = _best_addition(ranked, chosen, covered, used_words, max_words) or _best_addition(
            own_article, chosen, covered, used_words, max_words
        )
        if best is None:
            break
        chosen.append(best)
        covered |= best.terms
        used_words += best.words
    # The lead opens; sentences from its own article follow in their original order, then the other outlets'.
    rest = sorted(chosen[1:], key=lambda s: (s.source != lead.source, s.source, s.position))
    return [lead, *rest]


def _best_addition(
    candidates: list[_Sentence], chosen: list[_Sentence], covered: set[str], used_words: int, max_words: int
) -> Optional[_Sentence]:
    """Return the candidate that adds the most new facts without repeating the chosen sentences, or None."""
    best: Optional[_Sentence] = None
    best_value = 0.0
    for sentence in candidates:
        if any(sentence is picked for picked in chosen) or used_words + sentence.words > max_words:
            continue
        # Term coverage rather than weighted similarity, so that paraphrases of chosen sentences count as repeats
        # while sentences that only share the story's setting (names, dates) do not.
        overlap = len(sentence.terms & covered) / len(sentence.terms) if sentence.terms else 1.0
        # A sentence such as "She said..." may only follow the sentence it continues.
        continues = any(p.source == sentence.source and p.position == sentence.position - 1 for p in chosen)
        if (
            overlap >= REDUNDANCY_LIMIT
            or len(sentence.terms - covered) < MIN_NEW_TERMS
            or not (_stands_alone(sentence.text) or continues)
        ):
            continue
        value = sentence.score - REDUNDANCY_PENALTY * overlap
        if best is None or value > best_value:
            best, best_value = sentence, value
    return best


def _stands_alone(text: str) -> bool:
    first = text.split()[0]
    return (first[0].isupper() or first[0].isdigit()) and first.lower().strip("'’,") not in _DEPENDENT_STARTS


def _ends_with_abbreviation(text: str) -> bool:
    """True when text ends with a title, month, or initial such as "Nov.", which means its site cut it off."""
    last = text.split()[-1].rstrip("\"'”’)")
    stem = last[:-1]
    return last.endswith(".") and (stem.lower() in _TITLES_AND_MONTHS or (len(stem) == 1 and stem.isalpha()))





def _unit(weights: Mapping[str, float]) -> dict[str, float]:
    norm = math.sqrt(sum(weight * weight for weight in weights.values()))
    return {term: weight / norm for term, weight in weights.items()} if norm else {}


def _sum(vectors: Iterable[Mapping[str, float]]) -> dict[str, float]:
    total: dict[str, float] = defaultdict(float)
    for vector in vectors:
        for term, weight in vector.items():
            total[term] += weight
    return total


def _similarity(first: Mapping[str, float], second: Mapping[str, float]) -> float:
    """Cosine similarity of two unit vectors."""
    if len(first) > len(second):
        first, second = second, first
    return sum(weight * second.get(term, 0.0) for term, weight in first.items())
