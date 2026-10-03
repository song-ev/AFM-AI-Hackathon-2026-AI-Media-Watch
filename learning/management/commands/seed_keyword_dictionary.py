"""
Seed the code-word dictionary with realistic fraud slang so the leadership
"Динамика кодовых слов" widget has data to show (Stage-4 self-learning demo).

DEV ONLY — refuses to run with DEBUG=False so synthetic terms never land in a
production dictionary.

    python manage.py seed_keyword_dictionary
    python manage.py seed_keyword_dictionary --weeks 8 --clear
"""
import random
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from learning.models import KeywordDictionaryEntry as K

# Realistic fraud slang grouped by category.
TERMS = {
    "casino_slang": [
        "занос", "заносы", "крутить барабан", "поднял на ставках", "иксы",
        "лудка", "слил депо", "профит за минуту", "схема на авиаторе", "кэшаут",
        "фриспины", "вывел в плюс",
    ],
    "guarantee": [
        "гарантированный доход", "100% профит", "без риска", "вернём деньги",
        "доход каждый день", "пассивный доход", "стабильный плюс",
    ],
    "urgency": [
        "только сегодня", "осталось 3 места", "успей до конца дня",
        "набор закрывается", "последний шанс", "разбираем за час",
    ],
    "referral": [
        "по моей ссылке", "промокод в профиле", "пиши в личку", "реферальная",
        "приведи друга", "ссылка в шапке", "переходи в директ",
    ],
    "other": [
        "приватный канал", "сигналы", "инсайд", "закрытый чат",
    ],
}


class Command(BaseCommand):
    help = "Seed the code-word dictionary with demo fraud slang (DEV ONLY)."

    def add_arguments(self, parser):
        parser.add_argument("--weeks", type=int, default=8)
        parser.add_argument("--clear", action="store_true",
                            help="Delete existing entries first.")

    def handle(self, *args, **opts):
        if not settings.DEBUG:
            raise CommandError("Refusing to seed with DEBUG=False (production).")

        if opts["clear"]:
            K.objects.all().delete()

        rng = random.Random(7)
        now = timezone.now()
        weeks = opts["weeks"]
        created = 0

        for cat, terms in TERMS.items():
            for term in terms:
                if K.objects.filter(term__iexact=term).exists():
                    continue
                # Spread terms across the recent weeks so the chart shows growth.
                wk = rng.randint(0, weeks - 1)
                added = now - timedelta(weeks=wk, days=rng.randint(0, 6))
                auto = rng.random() < 0.6
                # Most are approved; some still pending review (auto-discovered).
                status = (K.Status.PENDING_REVIEW if (auto and rng.random() < 0.3)
                          else K.Status.APPROVED)
                K.objects.create(
                    term=term,
                    category=cat,
                    added_automatically=auto,
                    confirmation_count=rng.randint(5, 25) if auto else 0,
                    status=status,
                    added_at=added,
                )
                created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {created} dictionary terms across {len(TERMS)} categories "
            f"over {weeks} weeks. Total now: {K.objects.count()}."
        ))
