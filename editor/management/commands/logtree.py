from django.core.management.base import BaseCommand, LabelCommand, CommandError

from format import printout


class Command(BaseCommand):
        def handle(self, *args, **options):
                printout()

