from django.core.management.base import BaseCommand, LabelCommand, CommandError

from starrating.utils import db_init

class Command(BaseCommand):
	def handle(self, *args, **options):
		db_init.delete_all_ratings()
