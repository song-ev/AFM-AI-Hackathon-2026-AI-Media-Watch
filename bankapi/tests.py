"""Tests for the bank API: auth, risk lookup, performance, throttling."""
import secrets
import time
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from bankapi.models import BankApiKey, hash_api_key
from bankapi.services import evaluate_risk
from bankapi.throttling import BankApiKeyRateThrottle
from deepanalysis.models import DeepAnalysisResult
from incidents.models import Incident
from ingestion.models import Platform, SocialAccount, Video

RISK_CHECK_URL = "/api/bank/v1/risk-check/"


class BankApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.now = timezone.now()
        self.platform = Platform.objects.create(
            code=Platform.Code.INSTAGRAM, name="Instagram"
        )
        # bank_admin + API key
        self.bank_admin = User.objects.create_user(
            "bank_demo", password="pw", role=User.Role.BANK_ADMIN
        )
        self.raw_key = secrets.token_urlsafe(32)
        BankApiKey.objects.create(
            bank_admin=self.bank_admin,
            key_hash=hash_api_key(self.raw_key),
            prefix=self.raw_key[:8],
        )
        # A flagged account: linked phone -> incident with risk 90.
        self.account = SocialAccount.objects.create(
            platform=self.platform, external_id="acc-b", username="scam_kz",
            followers_count=1000, first_seen_at=self.now, last_seen_at=self.now,
            linked_payment_identifier="+77001234567",
        )
        video = Video.objects.create(
            platform=self.platform, social_account=self.account,
            external_id="vid-b", url="http://e/b", collected_at=self.now,
        )
        dar = DeepAnalysisResult.objects.create(
            video=video, started_at=self.now, risk_score=90.0
        )
        Incident.objects.create(
            video=video, deep_analysis_result=dar, risk_score=90.0
        )

    def _auth(self, key):
        return {"HTTP_AUTHORIZATION": f"ApiKey {key}"}

    def test_no_key_returns_401(self):
        resp = APIClient().post(
            RISK_CHECK_URL,
            {"account_identifier": "+77001234567", "identifier_type": "phone"},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_invalid_key_returns_401(self):
        resp = APIClient().post(
            RISK_CHECK_URL,
            {"account_identifier": "+77001234567", "identifier_type": "phone"},
            format="json", **self._auth("totally-wrong"),
        )
        self.assertEqual(resp.status_code, 401)

    def test_valid_key_match_returns_risk(self):
        resp = APIClient().post(
            RISK_CHECK_URL,
            {"account_identifier": "+77001234567", "identifier_type": "phone"},
            format="json", **self._auth(self.raw_key),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["is_flagged"])
        self.assertEqual(resp.data["risk_score"], 90.0)
        self.assertEqual(resp.data["related_incidents_count"], 1)
        self.assertIn("scheme_summary", resp.data)
        # Privacy: no internal detail leaks.
        for leaked in ("transcript", "evidence", "analyst", "video"):
            self.assertNotIn(leaked, resp.data)

    def test_no_match_not_flagged(self):
        resp = APIClient().post(
            RISK_CHECK_URL,
            {"account_identifier": "+70000000000", "identifier_type": "phone"},
            format="json", **self._auth(self.raw_key),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, {"is_flagged": False})

    def test_lookup_is_single_query(self):
        # The hot path itself must be one SQL query (auth overhead excluded).
        with CaptureQueriesContext(connection) as ctx:
            evaluate_risk("+77001234567", "phone")
        self.assertEqual(len(ctx.captured_queries), 1)

    def test_endpoint_latency_is_reasonable(self):
        client = APIClient()
        start = time.perf_counter()
        resp = client.post(
            RISK_CHECK_URL,
            {"account_identifier": "+77001234567", "identifier_type": "phone"},
            format="json", **self._auth(self.raw_key),
        )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        self.assertEqual(resp.status_code, 200)
        # Regression guard on the test DB — NOT a production SLA assertion.
        self.assertLess(elapsed_ms, 500, f"risk-check took {elapsed_ms:.0f}ms")
        self.assertIn("X-Response-Time-ms", resp)

    def test_throttle_kicks_in(self):
        cache.clear()
        client = APIClient()
        body = {"account_identifier": "+77001234567", "identifier_type": "phone"}
        # Force a low rate deterministically (the class reads `rate` directly).
        with patch.object(BankApiKeyRateThrottle, "rate", "2/min", create=True):
            codes = [
                client.post(RISK_CHECK_URL, body, format="json",
                            **self._auth(self.raw_key)).status_code
                for _ in range(3)
            ]
        self.assertEqual(codes[0], 200)
        self.assertEqual(codes[1], 200)
        self.assertEqual(codes[2], 429)

    def test_health_no_auth(self):
        resp = APIClient().get("/api/bank/v1/health/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "ok")
