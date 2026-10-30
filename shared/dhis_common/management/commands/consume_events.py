"""RabbitMQ consumer worker (only needed when RABBITMQ_URL is set).

Binds a durable queue to the 'dhis.events' topic exchange and passes each
message to settings.EVENT_HANDLER. A failed message is retried up to 5 times,
then rejected into the dead-letter queue 'dhis.dead'.
"""
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.module_loading import import_string

from dhis_common.events import EXCHANGE, process_once

DEAD_EXCHANGE = "dhis.dead"


class Command(BaseCommand):
    help = "Consume events from RabbitMQ."

    def handle(self, *args, **options):
        if not settings.RABBITMQ_URL:
            raise CommandError("RABBITMQ_URL is not set. The HTTP transport needs no worker.")
        import pika

        handler = import_string(settings.EVENT_HANDLER)
        queue = f"dhis.{settings.SERVICE_NAME}"
        connection = pika.BlockingConnection(pika.URLParameters(settings.RABBITMQ_URL))
        channel = connection.channel()
        channel.exchange_declare(EXCHANGE, "topic", durable=True)
        channel.exchange_declare(DEAD_EXCHANGE, "fanout", durable=True)
        channel.queue_declare("dhis.dead." + settings.SERVICE_NAME, durable=True)
        channel.queue_bind("dhis.dead." + settings.SERVICE_NAME, DEAD_EXCHANGE)
        channel.queue_declare(queue, durable=True, arguments={"x-dead-letter-exchange": DEAD_EXCHANGE})
        channel.queue_bind(queue, EXCHANGE, routing_key="#")

        def on_message(ch, method, properties, body):
            headers = properties.headers or {}
            attempts = int(headers.get("x-attempts", 0)) + 1
            try:
                process_once(json.loads(body), handler)
                ch.basic_ack(method.delivery_tag)
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f"failed ({attempts}/5): {exc}")
                if attempts < 5:
                    ch.basic_publish("", queue, body, pika.BasicProperties(delivery_mode=2, headers={"x-attempts": attempts}))
                    ch.basic_ack(method.delivery_tag)
                else:
                    ch.basic_nack(method.delivery_tag, requeue=False)  # goes to dead-letter queue

        channel.basic_qos(prefetch_count=10)
        channel.basic_consume(queue, on_message)
        self.stdout.write(f"consuming {queue}")
        channel.start_consuming()
