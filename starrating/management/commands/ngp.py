# New groups processing

from django.core.management.base import BaseCommand, LabelCommand, CommandError
from results import models
from django.db import connection

from starrating.aggr import  localtools

class Command(BaseCommand):
	def handle(self, *args, **options):
		localtools.create_all_zero_records_for_new_groups()
