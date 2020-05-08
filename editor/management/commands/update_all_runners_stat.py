# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand

from editor.views.views_stat import update_runners_stat

class Command(BaseCommand):
	help = 'Updates statistics for all runner for current year. Usually needs to run once a year, for base.probeg.org/runners'

	def add_arguments(self, parser):
		parser.add_argument('-f', '--from', type=int, default=0, help='First runner_id to work with')

	def handle(self, *args, **options):
		update_runners_stat(id_from=options['from'], debug=1)
