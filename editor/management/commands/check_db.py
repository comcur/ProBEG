# -*- coding: utf-8 -*-

from django.core.management.base import BaseCommand, LabelCommand, CommandError
from results import models
import json
import logging
import dbchecks.dbchecks


def check_db():
	logger = logging.getLogger('dbchecks')
	# logger = None   # - to disable logging

	##########################################
	# Cheking ForeignKeys and OneToOneFields #
	##########################################
	result = dbchecks.dbchecks.check_all_relationships2(logger)
	print json.dumps(result, sort_keys=True, indent=4, separators=(',', ': '))

	#####################
	# Checking equality #
	#####################
	check_list = [
#		(models.Klb_person, 'birthday', 'runner__birthday'), # disabled here
#		because datetime values cannot be outputed by json.dumps()
		(models.Klb_person, 'gender', 'runner__gender'),
		(models.Klb_result, 'event_raw_id', 'race__event_id'),
		(models.Klb_result, 'race_id', 'result__race_id'),
		(models.Klb_result, 'klb_person_id', 'klb_participant__klb_person_id'),
		(models.Klb_result, 'klb_person__runner__id', 'result__runner_id')  # Возможны, расхожения
	]

	result = dbchecks.dbchecks.check_equality_by_list(check_list, logger)
	print json.dumps(result, sort_keys=True, indent=4, separators=(',', ': '))

	check_list = [(models.Klb_person, 'birthday', 'runner__birthday')]
	result = dbchecks.dbchecks.check_equality_by_list(check_list, logger)
	print result

class Command(BaseCommand):
	def handle(self, *args, **options):
		check_db()
