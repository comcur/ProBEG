from django.core.management.base import BaseCommand, LabelCommand, CommandError
from starrating.aggr.updater import updater

import warnings
#warnings.simplefilter("error")
#warnings.simplefilter("ignore", DeprecationWarning)

class Command(BaseCommand):
	def handle(self, *args, **options):
		updater()
#		updater(mode='loop', only_one_group=True, pause=0)
#		updater(mode='one_pass', only_one_group=True, pause=0)
#		updater(mode='one_pass')
#		updater(mode='one_level')
