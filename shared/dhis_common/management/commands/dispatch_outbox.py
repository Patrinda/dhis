import time

from django.core.management.base import BaseCommand

from dhis_common.events import dispatch_once


class Command(BaseCommand):
    help = "Send pending outbox events. Use --loop to keep running as a worker."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true")

    def handle(self, *args, **options):
        while True:
            sent = dispatch_once()
            if sent:
                self.stdout.write(f"sent {sent} event(s)")
            if not options["loop"]:
                break
            time.sleep(1)
