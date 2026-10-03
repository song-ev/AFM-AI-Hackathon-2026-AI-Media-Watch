"""
Incident services: priority-score computation and freshness decay.

priority_score = Risk_Score × log(followers + 1) × e^(-hours_since_post / 48)

The exponential term decays with time, so priority must be recomputed
periodically (see the `recalculate_priorities` management command).
"""
import math

from django.utils import timezone

# Half-life-ish decay constant from the architecture formula (hours).
DECAY_HOURS = 48.0


def compute_priority_score(risk_score, followers_count, posted_at, now=None):
    """Pure implementation of the prioritisation formula.

    Args:
        risk_score: float 0-100.
        followers_count: account followers (>= 0).
        posted_at: when the video was posted (datetime) or None.
        now: reference time; defaults to timezone.now().

    Returns:
        The priority score as a float. Note log(followers+1) means an account
        with 0 followers yields 0 regardless of risk — this matches the formula.
    """
    now = now or timezone.now()
    if posted_at is not None:
        hours_since_post = max((now - posted_at).total_seconds() / 3600.0, 0.0)
    else:
        # Unknown post time → no decay applied.
        hours_since_post = 0.0
    followers = max(followers_count or 0, 0)
    return (
        float(risk_score)
        * math.log(followers + 1)
        * math.exp(-hours_since_post / DECAY_HOURS)
    )


def recalculate_pending_priorities(now=None):
    """Recompute priority_score for all pending_review incidents.

    Returns the number of incidents updated.
    """
    # Imported here to avoid a circular import at module load time.
    from incidents.models import Incident

    incidents = list(
        Incident.objects.select_related("video", "video__social_account").filter(
            status=Incident.Status.PENDING_REVIEW
        )
    )
    for incident in incidents:
        incident.recalculate_priority(save=False, now=now)
    if incidents:
        Incident.objects.bulk_update(incidents, ["priority_score"])
    return len(incidents)


# ---------------------------------------------------------------------------
# Connection graph (cross-platform identity network)
# ---------------------------------------------------------------------------
DEFAULT_GRAPH_NODE_LIMIT = 200
SUBGRAPH_HOPS = 2


def _account_key(account_id):
    return f"account:{account_id}"


def _identity_key(fp_id):
    return f"identity:{fp_id}"


def _promo_key(code):
    return f"promo:{code}"


def _telegram_key(url):
    return f"telegram:{url}"


def build_connection_graph(filters=None, limit=DEFAULT_GRAPH_NODE_LIMIT):
    """Aggregate the account/identity/promo/telegram connection graph.

    Edges are derived in bulk (values_list / joins), never per-edge in a loop.

    filters (all optional): account (username or id), promo_code, telegram_link,
    identity (fp id). When any filter is given, only the connected subnet
    (within SUBGRAPH_HOPS hops of the seed) is returned. Otherwise the graph is
    capped at `limit` nodes, keeping the highest-degree ones.
    """
    from deepanalysis.models import IdentityFingerprint, IdentityLink
    from incidents.models import PromoCode, TelegramLink
    from ingestion.models import SocialAccount

    filters = filters or {}

    # --- Bulk-fetch the raw relations --------------------------------------
    id_links = list(
        IdentityLink.objects.values_list("identity_fingerprint_id", "social_account_id")
    )
    promo_pairs = list(
        PromoCode.objects.values_list("code", "incident__video__social_account_id")
    )
    tg_pairs = list(
        TelegramLink.objects.values_list("url", "incident__video__social_account_id")
    )

    # --- Build typed edge set and node registry ----------------------------
    node_meta = {}  # key -> (type, raw_id)
    edges = set()

    def register(key, ntype, raw):
        node_meta[key] = (ntype, raw)
        return key

    # identity -> linked account ids (for the expandable list on identity nodes)
    identity_accounts = {}
    for fp_id, acc_id in id_links:
        ik = register(_identity_key(fp_id), "identity", fp_id)
        ak = register(_account_key(acc_id), "account", acc_id)
        edges.add((ik, ak))
        identity_accounts.setdefault(fp_id, []).append(acc_id)

    for code, acc_id in promo_pairs:
        ak = register(_account_key(acc_id), "account", acc_id)
        pk = register(_promo_key(code), "promo_code", code)
        edges.add((ak, pk))

    for url, acc_id in tg_pairs:
        ak = register(_account_key(acc_id), "account", acc_id)
        tk = register(_telegram_key(url), "telegram_link", url)
        edges.add((ak, tk))

    # --- Adjacency + degree -------------------------------------------------
    adjacency = {}
    degree = {}
    for a, b in edges:
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
        degree[a] = degree.get(a, 0) + 1
        degree[b] = degree.get(b, 0) + 1

    # --- Determine the selected node set -----------------------------------
    seeds = _resolve_seeds(filters, node_meta, SocialAccount)
    if seeds:
        selected = _bfs_neighbourhood(seeds, adjacency, SUBGRAPH_HOPS)
        # ensure isolated seeds still appear
        selected.update(seeds)
    else:
        all_keys = list(node_meta.keys())
        if len(all_keys) > limit:
            selected = set(sorted(
                all_keys, key=lambda k: degree.get(k, 0), reverse=True
            )[:limit])
        else:
            selected = set(all_keys)

    selected_edges = [
        {"from": a, "to": b} for (a, b) in edges if a in selected and b in selected
    ]

    # --- Fetch metadata only for nodes we will emit ------------------------
    account_ids = {raw for k in selected for (t, raw) in [node_meta[k]] if t == "account"}
    identity_ids = {raw for k in selected for (t, raw) in [node_meta[k]] if t == "identity"}
    # also need usernames for accounts referenced in identity expandable lists
    for fp_id in identity_ids:
        account_ids.update(identity_accounts.get(fp_id, []))

    acc_meta = {
        row[0]: row
        for row in SocialAccount.objects.filter(id__in=account_ids).values_list(
            "id", "username", "followers_count", "platform__code"
        )
    }
    fp_meta = dict(
        IdentityFingerprint.objects.filter(id__in=identity_ids).values_list(
            "id", "fingerprint_type"
        )
    )

    # --- Materialise nodes --------------------------------------------------
    nodes = []
    for key in selected:
        ntype, raw = node_meta[key]
        if ntype == "account":
            _id, username, followers, platform = acc_meta.get(
                raw, (raw, str(raw), 0, "")
            )
            nodes.append({
                "id": key,
                "type": "account",
                "label": username,
                "username": username,
                "followers_count": followers,
                "platform": platform,
            })
        elif ntype == "identity":
            ftype = fp_meta.get(raw, "voice")
            human = "голос" if ftype == "voice" else "лицо"
            linked = [
                {"id": _account_key(a), "username": acc_meta.get(a, (a, str(a)))[1]}
                for a in identity_accounts.get(raw, [])
            ]
            nodes.append({
                "id": key,
                "type": "identity",
                "label": f"Личность #{raw} ({human})",
                "fingerprint_type": ftype,
                "accounts": linked,
            })
        elif ntype == "promo_code":
            nodes.append({"id": key, "type": "promo_code", "label": raw, "code": raw})
        elif ntype == "telegram_link":
            nodes.append({"id": key, "type": "telegram_link", "label": raw, "url": raw})

    return {
        "nodes": nodes,
        "edges": selected_edges,
        "truncated": not seeds and len(node_meta) > len(selected),
    }


def _resolve_seeds(filters, node_meta, social_account_model):
    """Map filter params to seed node keys."""
    seeds = set()

    account = filters.get("account")
    if account:
        ids = list(
            social_account_model.objects.filter(username=account).values_list(
                "id", flat=True
            )
        )
        if not ids and str(account).isdigit():
            ids = [int(account)]
        for acc_id in ids:
            key = _account_key(acc_id)
            node_meta.setdefault(key, ("account", acc_id))
            seeds.add(key)

    if filters.get("promo_code"):
        key = _promo_key(filters["promo_code"])
        node_meta.setdefault(key, ("promo_code", filters["promo_code"]))
        seeds.add(key)

    if filters.get("telegram_link"):
        key = _telegram_key(filters["telegram_link"])
        node_meta.setdefault(key, ("telegram_link", filters["telegram_link"]))
        seeds.add(key)

    if filters.get("identity") and str(filters["identity"]).isdigit():
        fp_id = int(filters["identity"])
        key = _identity_key(fp_id)
        node_meta.setdefault(key, ("identity", fp_id))
        seeds.add(key)

    return seeds


def _bfs_neighbourhood(seeds, adjacency, hops):
    """Return all node keys within `hops` hops of any seed."""
    visited = set(seeds)
    frontier = set(seeds)
    for _ in range(hops):
        nxt = set()
        for node in frontier:
            nxt.update(adjacency.get(node, ()))
        nxt -= visited
        visited.update(nxt)
        frontier = nxt
        if not frontier:
            break
    return visited
