from django.core.management.base import BaseCommand
import datetime

from editor.views.views_age_group_record import generate_better_age_group_results

class Command(BaseCommand):
	help = 'Generates the list of results better than age group records'

	def handle(self, *args, **options):
		print datetime.datetime.now()
		generate_better_age_group_results()
		print datetime.datetime.now()