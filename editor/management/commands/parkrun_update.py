from django.core.management.base import BaseCommand
import datetime

from results import models
from editor.views.views_parkrun import update_parkrun_results

class Command(BaseCommand):
	help = 'Loads all not loaded Russian parkrun results'

	def handle(self, *args, **options):
		n_letters = update_parkrun_results(email=models.INFO_MAIL)
		self.stdout.write(self.style.SUCCESS('{}: {} letters were successfully sent.'.format(datetime.datetime.now(), n_letters)))
