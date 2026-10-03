"""
Train the Stage-4 risk classifier on demand (same logic as the weekly cycle).

    python manage.py train_risk_model
    python manage.py train_risk_model --min-examples 6 --show-importances
"""
from django.core.management.base import BaseCommand

from learning.training import feature_importances, train_risk_model


class Command(BaseCommand):
    help = "Train, validate and (if it does not regress) deploy a risk model."

    def add_arguments(self, parser):
        parser.add_argument("--min-examples", type=int, default=10,
                            help="Minimum labelled examples required before training.")
        parser.add_argument("--show-importances", action="store_true",
                            help="Print the trained feature weights, largest first.")

    def handle(self, *args, **options):
        run = train_risk_model(min_examples=options["min_examples"])

        self.stdout.write(f"Run #{run.id}: status={run.status}")
        self.stdout.write(f"  training examples : {run.training_examples_count}")
        if run.precision is not None:
            self.stdout.write(f"  precision         : {run.precision:.3f}")
            self.stdout.write(f"  recall            : {run.recall:.3f}")
            self.stdout.write(f"  false positive    : {run.false_positive_rate:.3f}")
        if run.notes:
            self.stdout.write(f"  notes             : {run.notes}")

        if options["show_importances"] and run.model_artifact:
            self.stdout.write("\nFeature importances (standardised weights):")
            for item in feature_importances(run):
                self.stdout.write(f"  {item['weight']:+.4f}  {item['feature']}")

        if run.is_active:
            self.stdout.write(self.style.SUCCESS("\nModel deployed and active."))
        else:
            self.stdout.write(self.style.WARNING(
                "\nModel not deployed (insufficient data or precision regression)."
            ))
