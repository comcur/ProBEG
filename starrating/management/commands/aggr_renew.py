from django.core.management.base import BaseCommand, LabelCommand, CommandError
from results import models
from django.db import connection

from starrating.aggr import globaltools, updater
from starrating.utils import db_init, fake_rating
from starrating.models import Method
from starrating.constants import CURRENT_METHOD


class Command(BaseCommand):
	def handle(self, *args, **options):
		globaltools.delete_aggregate_ratings(-1)
		m = Method.objects.get(pk=CURRENT_METHOD)
		m.is_actual = True
		m.save()
		db_init.mark_all_groups_new()
		updater.updater(mode='one_pass')
