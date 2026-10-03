"""Tests for the analyst queue API and prioritisation formula."""
import math
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AnalystLabel, AnalystProfile, User
from deepanalysis.models import (
    DeepAnalysisResult,
    FakeScreenshotDetection,
    IdentityFingerprint,
    IdentityLink,
    ReasoningNode,
    Transcript,
    TranscriptFlag,
)
from incidents.services import build_connection_graph
from incidents.models import (
    EvidenceChainEntry,
    Incident,
    PromoCode,
    TelegramLink,
)
from incidents.services import compute_priority_score
from ingestion.models import Platform, SocialAccount, Video
from screening.models import ScreeningResult, ScreeningSignal


class PriorityScoreTests(TestCase):
    """The formula: Risk × log(followers + 1) × e^(-hours / 48)."""

    def test_no_decay_when_posted_now(self):
        now = timezone.now()
        score = compute_priority_score(50, 999, now, now=now)
        self.assertAlmostEqual(score, 50 * math.log(1000) * math.exp(0), places=6)

    def test_zero_followers_yields_zero(self):
        now = timezone.now()
        # log(0 + 1) == 0, so the whole product is 0 regardless of risk.
        score = compute_priority_score(80, 0, now - timedelta(hours=10), now=now)
        self.assertAlmostEqual(score, 0.0, places=9)

    def test_decay_at_48_hours(self):
        now = timezone.now()
        posted = now - timedelta(hours=48)
        score = compute_priority_score(70, 100, posted, now=now)
        expected = 70 * math.log(101) * math.exp(-1.0)
        self.assertAlmostEqual(score, expected, places=6)

    def test_older_post_has_lower_priority(self):
        now = timezone.now()
        fresh = compute_priority_score(60, 500, now - timedelta(hours=2), now=now)
        stale = compute_priority_score(60, 500, now - timedelta(hours=72), now=now)
        self.assertGreater(fresh, stale)

    def test_missing_posted_at_applies_no_decay(self):
        now = timezone.now()
        score = compute_priority_score(40, 50, None, now=now)
        self.assertAlmostEqual(score, 40 * math.log(51), places=6)


class IncidentQueueAPITests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.platform = Platform.objects.create(
            code=Platform.Code.INSTAGRAM, name="Instagram"
        )
        self.account = SocialAccount.objects.create(
            platform=self.platform,
            external_id="acc-1",
            username="suspect_user",
            followers_count=100,
            first_seen_at=self.now,
            last_seen_at=self.now,
        )
        self.analyst = User.objects.create_user(
            "analyst1", password="pw", role=User.Role.ANALYST
        )
        self.bank = User.objects.create_user(
            "bank1", password="pw", role=User.Role.BANK_ADMIN
        )
        self._seq = 0

    def _make_incident(self, risk):
        self._seq += 1
        video = Video.objects.create(
            platform=self.platform,
            social_account=self.account,
            external_id=f"vid-{self._seq}",
            url=f"http://example.com/{self._seq}",
            collected_at=self.now,
        )
        dar = DeepAnalysisResult.objects.create(
            video=video, started_at=self.now, risk_score=risk
        )
        return Incident.objects.create(
            video=video, deep_analysis_result=dar, risk_score=risk
        )

    def test_risk_score_range_filter(self):
        self._make_incident(10)
        self._make_incident(50)
        self._make_incident(90)
        client = APIClient()
        client.force_authenticate(self.analyst)

        resp = client.get("/api/incidents/?risk_score_min=40&risk_score_max=80")
        self.assertEqual(resp.status_code, 200)
        results = resp.data["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["risk_score"], 50)

    def test_default_ordering_by_priority_desc(self):
        low = self._make_incident(10)
        high = self._make_incident(90)
        low.priority_score = 1.0
        low.save(update_fields=["priority_score"])
        high.priority_score = 99.0
        high.save(update_fields=["priority_score"])

        client = APIClient()
        client.force_authenticate(self.analyst)
        resp = client.get("/api/incidents/")
        ids = [row["id"] for row in resp.data["results"]]
        self.assertEqual(ids, [high.id, low.id])

    def test_bank_admin_forbidden(self):
        self._make_incident(50)
        client = APIClient()
        client.force_authenticate(self.bank)
        resp = client.get("/api/incidents/")
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_forbidden(self):
        resp = APIClient().get("/api/incidents/")
        self.assertIn(resp.status_code, (401, 403))

    def test_stats_endpoint(self):
        self._make_incident(20)
        self._make_incident(40)
        client = APIClient()
        client.force_authenticate(self.analyst)
        resp = client.get("/api/incidents/stats/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["queue_total"], 2)
        self.assertEqual(resp.data["status_breakdown"]["pending_review"], 2)
        self.assertAlmostEqual(resp.data["avg_risk_score_24h"], 30.0)


class IncidentDetailAPITests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.analyst = User.objects.create_user(
            "analyst2", password="pw", role=User.Role.ANALYST
        )
        self.bank = User.objects.create_user(
            "bank2", password="pw", role=User.Role.BANK_ADMIN
        )
        self.incident = self._make_rich_incident()

    def _make_rich_incident(self):
        platform = Platform.objects.create(
            code=Platform.Code.TIKTOK, name="TikTok"
        )
        account = SocialAccount.objects.create(
            platform=platform, external_id="acc-d", username="scammer",
            followers_count=5000, first_seen_at=self.now, last_seen_at=self.now,
        )
        video = Video.objects.create(
            platform=platform, social_account=account, external_id="vid-d",
            url="http://example.com/d", caption="win big now",
            collected_at=self.now,
        )
        screening = ScreeningResult.objects.create(
            video=video, status=ScreeningResult.Status.SUSPICIOUS,
            triggered_at=self.now,
        )
        for module in (ScreeningSignal.Module.METADATA,
                       ScreeningSignal.Module.QUICK_AUDIO):
            ScreeningSignal.objects.create(
                screening_result=screening, module=module,
                is_triggered=True, confidence=0.8,
            )
        dar = DeepAnalysisResult.objects.create(
            video=video, started_at=self.now, risk_score=77.0,
        )
        transcript = Transcript.objects.create(
            deep_analysis_result=dar, full_text="...", language="ru",
        )
        for phrase in ("guaranteed profit", "act now"):
            TranscriptFlag.objects.create(
                transcript=transcript, phrase=phrase,
                start_sec=1.0, end_sec=2.0,
                category=TranscriptFlag.Category.GUARANTEE, severity=0.9,
            )
        FakeScreenshotDetection.objects.create(
            deep_analysis_result=dar, frame_timestamp_sec=3.0,
            bank_name="Kaspi", is_fake=True, confidence=0.95,
            artifacts_found=["font_mismatch"],
        )
        for key in ("audio_quick_scan", "verdict"):
            ReasoningNode.objects.create(
                deep_analysis_result=dar, node_key=key, label=key,
                node_type=ReasoningNode.NodeType.STAGE2_SIGNAL,
                status=ReasoningNode.Status.TRIGGERED,
                score_contribution=10.0,
            )
        incident = Incident.objects.create(
            video=video, deep_analysis_result=dar, risk_score=77.0,
            summary_text="Suspicious casino promo.",
        )
        for i in range(2):
            EvidenceChainEntry.objects.create(
                incident=incident, file_type=EvidenceChainEntry.FileType.VIDEO,
                file_path=f"/data/{i}.mp4", sha256_hash=f"hash{i}" * 8,
                collected_at=self.now, collection_method="yt-dlp automated download",
            )
        PromoCode.objects.create(
            incident=incident, code="LUCKY777",
            extracted_from=PromoCode.Source.CAPTION,
        )
        TelegramLink.objects.create(
            incident=incident, url="https://t.me/casino",
            extracted_from=TelegramLink.Source.CAPTION,
        )
        return incident

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def test_detail_card_returns_all_sections(self):
        resp = self._client(self.analyst).get(f"/api/incidents/{self.incident.id}/")
        self.assertEqual(resp.status_code, 200)
        data = resp.data
        self.assertEqual(data["summary_text"], "Suspicious casino promo.")
        self.assertEqual(data["video"]["external_id"], "vid-d")
        self.assertEqual(data["social_account"]["username"], "scammer")
        self.assertEqual(len(data["transcript_flags"]), 2)
        self.assertEqual(len(data["fake_screenshots"]), 1)
        self.assertEqual(len(data["evidence_chain"]), 2)
        self.assertEqual(len(data["promo_codes"]), 1)
        self.assertEqual(len(data["telegram_links"]), 1)
        # risk_breakdown aggregates reasoning nodes (2) + screening signals (2)
        self.assertEqual(len(data["risk_breakdown"]), 4)

    def test_detail_card_query_count_is_bounded(self):
        client = self._client(self.analyst)
        with CaptureQueriesContext(connection) as ctx:
            resp = client.get(f"/api/incidents/{self.incident.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertLess(
            len(ctx.captured_queries), 15,
            f"Too many queries: {len(ctx.captured_queries)}",
        )

    def test_submit_decision_updates_status_and_count(self):
        client = self._client(self.analyst)
        resp = client.post(
            f"/api/incidents/{self.incident.id}/decision/",
            {"decision": "confirmed", "comment": "clear fraud"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "confirmed")
        self.assertEqual(len(resp.data["analyst_labels"]), 1)

        self.incident.refresh_from_db()
        self.assertEqual(self.incident.status, Incident.Status.CONFIRMED)
        self.assertEqual(
            AnalystLabel.objects.filter(incident=self.incident).count(), 1
        )
        profile = AnalystProfile.objects.get(user=self.analyst)
        self.assertEqual(profile.cases_reviewed_count, 1)

    def test_invalid_decision_rejected(self):
        client = self._client(self.analyst)
        resp = client.post(
            f"/api/incidents/{self.incident.id}/decision/",
            {"decision": "not_a_choice"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_bank_admin_forbidden_on_detail_and_decision(self):
        client = self._client(self.bank)
        self.assertEqual(
            client.get(f"/api/incidents/{self.incident.id}/").status_code, 403
        )
        self.assertEqual(
            client.post(
                f"/api/incidents/{self.incident.id}/decision/",
                {"decision": "confirmed"}, format="json",
            ).status_code,
            403,
        )

    def test_evidence_chain_json_and_text(self):
        client = self._client(self.analyst)
        json_resp = client.get(
            f"/api/incidents/{self.incident.id}/evidence-chain/"
        )
        self.assertEqual(json_resp.status_code, 200)
        self.assertEqual(len(json_resp.data["entries"]), 2)

        text_resp = client.get(
            f"/api/incidents/{self.incident.id}/evidence-chain/?format=text"
        )
        self.assertEqual(text_resp.status_code, 200)
        self.assertEqual(text_resp["Content-Type"], "text/plain; charset=utf-8")
        body = text_resp.content.decode()
        self.assertIn("EVIDENCE CHAIN OF CUSTODY", body)
        self.assertIn("yt-dlp automated download", body)


class ConnectionGraphTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.platform = Platform.objects.create(
            code=Platform.Code.INSTAGRAM, name="Instagram"
        )
        self.analyst = User.objects.create_user(
            "analyst4", password="pw", role=User.Role.ANALYST
        )
        self.bank = User.objects.create_user(
            "bank4", password="pw", role=User.Role.BANK_ADMIN
        )
        self._seq = 0

    def _account(self, username, followers=10):
        self._seq += 1
        return SocialAccount.objects.create(
            platform=self.platform, external_id=f"acc-{self._seq}",
            username=username, followers_count=followers,
            first_seen_at=self.now, last_seen_at=self.now,
        )

    def _incident_for(self, account):
        self._seq += 1
        video = Video.objects.create(
            platform=self.platform, social_account=account,
            external_id=f"vid-{self._seq}", url=f"http://e/{self._seq}",
            collected_at=self.now,
        )
        dar = DeepAnalysisResult.objects.create(video=video, started_at=self.now)
        return Incident.objects.create(video=video, deep_analysis_result=dar)

    def test_three_accounts_collapse_into_one_identity(self):
        accounts = [self._account(f"user{i}") for i in range(3)]
        fp = IdentityFingerprint.objects.create(
            fingerprint_type=IdentityFingerprint.FingerprintType.VOICE,
            embedding_hash="abc123",
        )
        for acc in accounts:
            IdentityLink.objects.create(
                identity_fingerprint=fp, social_account=acc, linked_at=self.now
            )

        graph = build_connection_graph()
        identity_nodes = [n for n in graph["nodes"] if n["type"] == "identity"]
        account_nodes = [n for n in graph["nodes"] if n["type"] == "account"]

        self.assertEqual(len(identity_nodes), 1)
        self.assertEqual(len(identity_nodes[0]["accounts"]), 3)
        self.assertEqual(len(account_nodes), 3)
        # one identity->account edge per account
        self.assertEqual(len(graph["edges"]), 3)

    def test_shared_promo_code_links_accounts(self):
        a1 = self._account("seller_a")
        a2 = self._account("seller_b")
        for acc in (a1, a2):
            incident = self._incident_for(acc)
            PromoCode.objects.create(
                incident=incident, code="BONUS50",
                extracted_from=PromoCode.Source.CAPTION,
            )

        graph = build_connection_graph()
        promo_nodes = [n for n in graph["nodes"] if n["type"] == "promo_code"]
        self.assertEqual(len(promo_nodes), 1)
        self.assertEqual(promo_nodes[0]["code"], "BONUS50")
        # the promo node connects both accounts
        promo_id = promo_nodes[0]["id"]
        neighbours = {
            e["from"] if e["to"] == promo_id else e["to"]
            for e in graph["edges"]
            if promo_id in (e["from"], e["to"])
        }
        self.assertEqual(len(neighbours), 2)

    def test_filter_returns_only_connected_subnet(self):
        # Connected cluster via identity.
        cluster = [self._account(f"c{i}") for i in range(2)]
        fp = IdentityFingerprint.objects.create(
            fingerprint_type=IdentityFingerprint.FingerprintType.FACE,
            embedding_hash="cluster",
        )
        for acc in cluster:
            IdentityLink.objects.create(
                identity_fingerprint=fp, social_account=acc, linked_at=self.now
            )
        # Unrelated isolated account with its own identity.
        other = self._account("unrelated")
        fp2 = IdentityFingerprint.objects.create(
            fingerprint_type=IdentityFingerprint.FingerprintType.VOICE,
            embedding_hash="other",
        )
        IdentityLink.objects.create(
            identity_fingerprint=fp2, social_account=other, linked_at=self.now
        )

        graph = build_connection_graph({"account": "c0"})
        usernames = {n["username"] for n in graph["nodes"] if n["type"] == "account"}
        self.assertIn("c0", usernames)
        self.assertIn("c1", usernames)  # sibling via shared identity (2 hops)
        self.assertNotIn("unrelated", usernames)

    def test_search_autocomplete(self):
        self._account("kazcasino_official")
        acc = self._account("promo_master")
        incident = self._incident_for(acc)
        PromoCode.objects.create(
            incident=incident, code="KAZ777",
            extracted_from=PromoCode.Source.CAPTION,
        )
        client = APIClient()
        client.force_authenticate(self.analyst)

        resp = client.get("/api/connections/search/?q=kaz")
        self.assertEqual(resp.status_code, 200)
        types = {(r["type"], r["value"]) for r in resp.data["results"]}
        self.assertIn(("account", "kazcasino_official"), types)
        self.assertIn(("promo_code", "KAZ777"), types)

    def test_graph_endpoint_and_bank_forbidden(self):
        self._account("solo")
        analyst_client = APIClient()
        analyst_client.force_authenticate(self.analyst)
        self.assertEqual(
            analyst_client.get("/api/connections/graph/").status_code, 200
        )

        bank_client = APIClient()
        bank_client.force_authenticate(self.bank)
        self.assertEqual(
            bank_client.get("/api/connections/graph/").status_code, 403
        )


class DashboardPermissionTests(TestCase):
    ENDPOINTS = [
        "/api/dashboard/trends/",
        "/api/dashboard/geography/",
        "/api/dashboard/keyword-trends/",
        "/api/dashboard/roi/",
    ]

    def setUp(self):
        cache.clear()
        self.analyst = User.objects.create_user(
            "analyst5", password="pw", role=User.Role.ANALYST
        )
        self.bank = User.objects.create_user(
            "bank5", password="pw", role=User.Role.BANK_ADMIN
        )

    def test_analyst_allowed_on_all_dashboards(self):
        client = APIClient()
        client.force_authenticate(self.analyst)
        for url in self.ENDPOINTS:
            self.assertEqual(client.get(url).status_code, 200, url)

    def test_bank_admin_forbidden_on_all_dashboards(self):
        client = APIClient()
        client.force_authenticate(self.bank)
        for url in self.ENDPOINTS:
            self.assertEqual(client.get(url).status_code, 403, url)
