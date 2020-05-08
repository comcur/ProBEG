from django.core.management.base import BaseCommand, LabelCommand, CommandError
from results import models
from django.db import connection

from starrating.aggr import checkers, globaltools
from starrating.utils import db_init, fake_rating


def test_get_params_to_rate_for_race(command_self):
	race_id=123
	
	race = models.Race.objects.select_related('distance').only(
			'distance__distance_type',
			'distance__length',
		).get(pk=race_id)
	
	pars = vs.get_params_to_rate_for_race(race_id)
	
	for p in pars:
		print p.id, p.name


class Command(BaseCommand):
	def handle(self, *args, **options):
#		db_init.delete_all_ratings()
#		db_init.make_rating_parameters()
#		db_init.make_methods()
#		fake_rating.generate_sample_primary_ratings(90.0)
#		fake_rating.generate_random_primary_ratings(80.0, 80.0)

#		globaltools.delete_aggregate_ratings(-1)

#		globaltools.create_all_zero_records_for_metod(1)
#		globaltools.calculate_aggregate_values_for_method(1)

#		globaltools.create_all_zero_records_for_metod(9)
#		globaltools.make_fake_aggregate_values_for_method(9)

#		checkers.check_relationship_structure_of_aggregate_models()
#		checkers.check_method_1()
