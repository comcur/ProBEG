from django.core.management.base import BaseCommand

from results import models
from editor.views import views_protocol

def load_chicago_2013_men():
	column_data_types = [0] * 12
	column_data_types[0] = views_protocol.CELL_DATA_PLACE
	column_data_types[1] = views_protocol.CELL_DATA_PLACE_GENDER
	column_data_types[2] = views_protocol.CELL_DATA_PLACE_CATEGORY
	column_data_types[3] = views_protocol.CELL_DATA_LNAME
	column_data_types[4] = views_protocol.CELL_DATA_FNAME
	column_data_types[5] = views_protocol.CELL_DATA_COUNTRY
	column_data_types[6] = views_protocol.CELL_DATA_CITY
	column_data_types[7] = views_protocol.CELL_DATA_BIB
	column_data_types[8] = views_protocol.CELL_DATA_CATEGORY
	column_data_types[9] = views_protocol.CELL_DATA_AGE
	column_data_types[10] = views_protocol.CELL_DATA_SPLIT
	column_data_types[11] = views_protocol.CELL_DATA_RESULT

	column_split_values = [0] * 12
	column_split_values[10] = 127
	views_protocol.process_protocol(
		event_id=4855,
		sheet_index=0,
		column_data_types=column_data_types,
		column_split_values=column_split_values,
		genders=[0] * 30000,
		try_load_results=True
	)

def load_chicago_2013_women():
	column_data_types = [0] * 12
	column_data_types[0] = views_protocol.CELL_DATA_PLACE
	column_data_types[1] = views_protocol.CELL_DATA_PLACE_GENDER
	column_data_types[2] = views_protocol.CELL_DATA_PLACE_CATEGORY
	column_data_types[3] = views_protocol.CELL_DATA_LNAME
	column_data_types[4] = views_protocol.CELL_DATA_FNAME
	column_data_types[5] = views_protocol.CELL_DATA_COUNTRY
	column_data_types[6] = views_protocol.CELL_DATA_CITY
	column_data_types[7] = views_protocol.CELL_DATA_BIB
	column_data_types[8] = views_protocol.CELL_DATA_CATEGORY
	column_data_types[9] = views_protocol.CELL_DATA_AGE
	column_data_types[10] = views_protocol.CELL_DATA_SPLIT
	column_data_types[11] = views_protocol.CELL_DATA_RESULT

	column_split_values = [0] * 12
	column_split_values[10] = 127
	views_protocol.process_protocol(
		event_id=4855,
		sheet_index=1,
		column_data_types=column_data_types,
		column_split_values=column_split_values,
		genders=[1] * 30000,
		save_old_results=True,
		try_load_results=True
	)

def load_mm_2015():
	views_protocol.process_protocol(
		race_id=9647,
		sheet_index=0,
		try_load_results=True
	)

def load_mm_2014():
	views_protocol.process_protocol(
		race_id=8012,
		sheet_index=0,
		try_load_results=True
	)

def load_minsk_polo_2016():
	column_data_types = [0] * 8
	column_data_types[0] = views_protocol.CELL_DATA_PLACE
	column_data_types[1] = views_protocol.CELL_DATA_BIB
	column_data_types[2] = views_protocol.CELL_DATA_PLACE_GENDER
	column_data_types[3] = views_protocol.CELL_DATA_LNAME
	column_data_types[4] = views_protocol.CELL_DATA_FNAME
	column_data_types[5] = views_protocol.CELL_DATA_GENDER
	column_data_types[6] = views_protocol.CELL_DATA_CLUB
	column_data_types[7] = views_protocol.CELL_DATA_RESULT
	settings = {}
	settings['categories'] = [''] * 9920
	views_protocol.process_protocol(
		race_id=18890,
		sheet_index=2,
		column_data_types=column_data_types,
		settings=settings,
		try_load_results=True
	)

def load_bryansk_2017():
	views_protocol.process_protocol(
		race_id=24948,
		# try_load_results=True
	)

def load_hearts_2017():
	views_protocol.process_protocol(
		race_id=26640,
		sheet_index=3,
		try_load_results=True
	)

def load_wn_2017():
	views_protocol.process_protocol(
		race_id=23783,
		sheet_index=1,
		try_load_results=True,
		settings={'try_get_gender_from_group': True}
	)

def load_mm_2017():
	views_protocol.process_protocol(
		race_id=26090,
		sheet_index=0,
		try_load_results=False,
		settings={'save_old_results': views_protocol.OLD_RESULTS_DELETE_ALL},	
	)
def load_mm_2017_10k():
	views_protocol.process_protocol(
		race_id=26089,
		sheet_index=1,
		try_load_results=True
	)

BOOLEAN_PARAMS = ('try_load', 'try_get_gender_from_group', 'all_are_male', 'all_are_female')
class Command(BaseCommand):
	help = 'Loads results from XLS/XLSX protocol'

	def add_arguments(self, parser):
		parser.add_argument('--race', type=int, required=True)
		parser.add_argument('--sheet', type=int, default=0)
		parser.add_argument('--delete_old_results', action='store_true')
		for param in BOOLEAN_PARAMS:
			parser.add_argument('--' + param, action='store_true')

	def handle(self, *args, **options):
		# print 'Trying to call process_protocol with race_id', options['race'], ', sheet index', options['sheet'], ', try to load? ', options['try_load']
		# if options['delete_old_results']:
		# 	print 'Trying to delete old results!!'
		settings = {}
		if options['delete_old_results']:
			settings['save_old_results'] = views_protocol.OLD_RESULTS_DELETE_ALL
		for param in BOOLEAN_PARAMS:
			settings[param] = True if options[param] else False
		if settings['all_are_male'] and settings['all_are_female']:
			print 'You cannot specify --all_are_male and --all_are_female at the same time.'
			return
		views_protocol.process_protocol(
			race_id=options['race'],
			sheet_index=options['sheet'],
			settings=settings
		)
