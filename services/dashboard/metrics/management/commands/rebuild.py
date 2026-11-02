"""Rebuild every dashboard number by replaying the stored events in order."""
from django.core.management.base import BaseCommand
from django.db import transaction

from metrics import handlers
from metrics.models import ConditionCount, DailyCount, EventRecord, TransferProjection


class Command(BaseCommand):
    help = "Delete all projections and rebuild them from the stored event log."

    def handle(self, *args, **options):
        with transaction.atomic():
            for model in (ConditionCount, DailyCount, TransferProjection):
                model.objects.all().delete()
            count = 0
            for event in EventRecord.objects.order_by("occurred_at", "id"):
                handlers.apply(event.event_type, event.version, event.occurred_at, event.payload)
                count += 1
        self.stdout.write(self.style.SUCCESS(f"Rebuilt from {count} events."))
