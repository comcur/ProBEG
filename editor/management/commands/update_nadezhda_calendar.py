# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand

from results.results_util import restart_django
from editor.views.views_stat import generate_events_in_seria_by_year2

class Command(BaseCommand):
	help = 'Updates the full list of Russian series with all events in last three years'

	def handle(self, *args, **options):
		generate_events_in_seria_by_year2()
		restart_django()
		print('Finished!')
		