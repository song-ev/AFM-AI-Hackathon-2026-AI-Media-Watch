import unicodedata
from rapidfuzz import fuzz, process
from learning.models import KeywordDictionaryEntry

# Hardcoded base list from the document.
BASE_KEYWORDS = [
    "казино", "слот", "ставка", "гарантия", "авиатор", "lucky jet",
    "1xbet", "бинго", "рулетка", "депозит", "вывод", "каспи",
    "гарантированный доход", "100% прибыль", "только сегодня",
    "осталось мест"
]

def normalize_text(text: str) -> str:
    """Normalize unicode and lowercase."""
    if not text:
        return ""
    return unicodedata.normalize('NFKD', text).lower()

def match_keywords(text: str, threshold: float = 85.0) -> list[dict]:
    """
    Fuzzy match text against both approved dynamic keywords and a hardcoded list.
    Returns: list of dicts: {"term": str, "matched_text": str, "score": float}
    """
    norm_text = normalize_text(text)
    if not norm_text:
        return []
        
    words = norm_text.split()
    
    # Gather dictionary
    approved_entries = KeywordDictionaryEntry.objects.filter(
        status=KeywordDictionaryEntry.Status.APPROVED
    ).values_list('term', flat=True)
    
    all_terms = set(BASE_KEYWORDS) | set(approved_entries)
    
    matches = []
    
    # Simple token-based fuzzy matching
    for term in all_terms:
        norm_term = normalize_text(term)
        
        # Try extractOne if it's a single word term, or partial_ratio for phrases
        if len(norm_term.split()) == 1 and words:
            best_match = process.extractOne(
                norm_term, words, scorer=fuzz.ratio, score_cutoff=threshold
            )
            if best_match:
                matched_str, score, _ = best_match
                matches.append({
                    "term": term,
                    "matched_text": matched_str,
                    "score": score
                })
                continue
        
        # Try partial ratio on the whole text for multi-word terms
        score = fuzz.partial_ratio(norm_term, norm_text)
        if score >= threshold:
            matches.append({
                "term": term,
                "matched_text": "phrase match", # Cannot easily pinpoint exact string with partial_ratio without more complex logic
                "score": score
            })
            
    # Deduplicate by term
    unique_matches = {}
    for m in matches:
        if m["term"] not in unique_matches or unique_matches[m["term"]]["score"] < m["score"]:
            unique_matches[m["term"]] = m
            
    return list(unique_matches.values())
