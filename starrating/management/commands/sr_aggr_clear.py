from django.core.management.base import BaseCommand, LabelCommand, CommandError

import logging
from starrating.aggr import globaltools

class Command(BaseCommand):
	def handle(self, *args, **options):
		globaltools.delete_aggregate_ratings(-1)
