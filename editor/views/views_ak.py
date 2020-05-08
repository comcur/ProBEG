# -*- coding: utf-8 -*-
from __future__ import division
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.models import User
import datetime

from results import models, models_ak
from .views_common import group_required, write_log
from .views_result import get_first_name_position, split_name, fill_places, fill_race_headers
from .views_distance import pair2type_length
from .views_stat import update_results_count

# Distances to create
@group_required('admins')
def add_distances_from_ak_rezult(request):
	# ak_race_ids_to_load = sorted(set(models_ak.CUR_AK_RESULT_MODEL.objects.filter(is_in_v1=2).values_list(
	# 	'ak_race__id', flat=True)))
	ak_race_ids_to_load = sorted(set(models.Race.objects.exclude(event__ak_race_id='').filter(
		loaded=0).order_by('event__ak_race_id').values_list('event__ak_race_id', flat=True)))
	#['AB0000']
	races_added = 0
	report = ""
	report_dists = []

	write_log("\nNew import. Now: " + str(datetime.datetime.now()) + "\n")

	for ak_race_id in ak_race_ids_to_load:
		events = models.Event.objects.filter(ak_race_id=ak_race_id)
		if events.count() > 1:
			report += write_log(u'Найдено больше одного события с RACEID="{}". Пропускаем.'.format(ak_race_id)) + "<br/>"
			continue
		event = events.first()
		if event is None:
			report += write_log(u'Не найдено событие с RACEID="{}". Пропускаем.'.format(ak_race_id)) + "<br/>"
			continue
		distances = models.Distance.objects.filter(race__event=event)
		distances_in_races = set(distances.values_list('distance_type', 'length'))
		distances_in_races_names = distances.order_by('-length').values_list('name', flat=True)
		distances_in_ak_result = set(models_ak.CUR_AK_RESULT_MODEL.objects.filter(ak_race__id=ak_race_id).values_list(
			'distance', flat=True))
		distances_absent = []
		for distance in distances_in_ak_result:
			distance = distance.replace(",", ".")
			if distance == u"20 км(2 кр":
				distance = u"20 км"
			if distance == u"20 км-сокр":
				distance = u"20 км"
			if distance == u"21. 0975 к":
				distance = u"21.0975 км"
			if distance == u"21. 1 км":
				distance = u"21.1 км"
			if distance == u"42.195":
				distance = u"42.195 км"
			#res, to_break = process_distance(distance)
			res = distance.strip()
			#if to_break:
			#	distances_absent.append(distance)
			res_split = res.split()
			#if len(res_split) != 2 or models.float_safe(res_split[0]) == 0:
			#	distances_absent.append(distance)
			dist_type, length = pair2type_length(models.float_safe(res_split[0]), res_split[1])
			if (dist_type, length) in distances_in_races:
				distance_to_use = (dist_type, length)
			elif dist_type == 1 and (42000 <= length <= 42200) and ((1, 42195) in distances_in_races):
				distance_to_use = (1, 42195)
			elif dist_type == 1 and (21000 <= length <= 21100) and ((1, 21098) in distances_in_races):
				distance_to_use = (1, 21098)
			else:
				distances_absent.append(distance)
				# new_dist = models.Distance.objects.get(distance_type=dist_type, length=length)
				# new_race = Race(event=event, distance=new_dist, series_raw=event.series.id,
				# 	distance_raw=new_dist.distance_raw, race_type_raw=new_dist.race_type_raw)
				# new_race.save()
				# races_added += 1

		if distances_absent:
			report_dists.append((ak_race_id, event.start_date, event.series.id,
				", ".join([unicode(x) for x in distances_in_races_names]),
				", ".join([unicode(x) for x in distances_absent]),
				", ".join([unicode(x) for x in distances_in_ak_result]),
				))


	write_log("Import finished. Now: " + str(datetime.datetime.now()) + "\n")

	context = {}
	context['races_added'] = races_added
	context['report'] = report
	context['report_dists'] = report_dists

	return render(request, "editor/results_import.html", context)

def process_ak_status(status): # RESULT field to our status
	status = status.upper()
	if status.startswith(('DSQ', 'DNQ', 'DQ', u'ДИСК', u'СНЯТ', u'(СНЯТ', u'РЕЗ АН', u'РЕЗ.АН', u'РЕЗ. АН', u'СЕЯТ', u'СН.')):
		return models.STATUS_DSQ
	elif status.startswith(('DNS', u'НЕ СТА', u'Н/Я', u'Н\Я', u'Н/С', u'НС', u'Н\С', u'НЕЯВ', u'-', u'—', u'НЕ ВЫШ',
		u'НЕ ПРИ', u'НЕ СТ', u'НЕ ЯВ', u'СХОД')):
		return models.STATUS_DNS
	# if status.startswith(('DNF', u'СОШ', u'(СОШ', u'СОЩЛА', u'НЕ ФИ', u'ВЫБЫЛ', u'Н/Ф', u'НЕ ЗАК', u'НЕ ДОБ', u'НЕ ПОЛ',
	#		u'НЕПОЛН', u'НЕФИН')):
	return models.STATUS_DNF

def create_result_from_ak(user, race, ak_result, first_name_position, to_log_action=False):
	#if debug:
	#	messages.success(request, u'Грузим человека {}.'.format(ak_result.name_raw))
	ak_person = ak_result.ak_person
	# Runner always should be found, not created: we must add all new runners from AK before importing results from AK
	runner, created = models.Runner.objects.get_or_create(
		ak_person=ak_person,
		defaults={'lname': ak_person.lname, 'fname': ak_person.fname, 'city': ak_person.city,
			'gender': models.GENDER_MALE if ak_person.gender_raw.lower() == u'м' else models.GENDER_FEMALE}
	)
	result = models.Result(
		race=race,
		runner=runner,
		ak_person=ak_result.ak_person,
		name_raw=ak_result.name_raw.strip(),
		time_raw=ak_result.time_raw.strip(),
		country_raw=ak_result.country_raw.strip(),
		city_raw=ak_result.city_raw.strip(),
		club_raw=ak_result.club_raw.strip(),
		birthday_raw=ak_result.birthday_raw,
		birthyear_raw=ak_result.birthyear_raw,
		place_raw=ak_result.place,
		place_category_raw=ak_result.place_category,
		age_raw=ak_result.age_raw,
		category=ak_result.category.strip(),
		comment_raw=ak_result.comment.strip(),
		bib=ak_result.bib.strip()
		)
	result.country_name = result.country_raw
	result.city_name = result.city_raw
	result.club_name = result.club_raw
	result.age = result.age_raw
	result.comment = result.comment_raw
	if ak_result.result == 0 or ak_result.result == 99999.9:
		result.status = process_ak_status(result.time_raw)
	else:
		if race.distance.distance_type == models.TYPE_MINUTES:
			result.result = round(float(race.distance.length) * 60 * 10000 / ak_result.result)
		else:
			result.result = round(ak_result.result * 100)
	if ak_result.birthday_raw is None:
		result.birthday_known = False
		if ak_result.birthyear_raw is None:
			result.birthday = None
		else:
			result.birthday = datetime.date(ak_result.birthyear_raw, 1, 1)
	else:
		result.birthday_known = True
		result.birthday = ak_result.birthday_raw
	result.lname, result.fname, result.midname = split_name(result.name_raw, first_name_position)
	result.gender = models.string2gender(ak_result.ak_person.gender_raw) if ak_result.ak_person else models.GENDER_UNKNOWN
	result.loaded_by = user
	result.loaded_from = "AK55: table {}, RACEID {}, result id {}".format(ak_result.__class__._meta.db_table, ak_result.ak_race.id, ak_result.id)
	result.save()
	if to_log_action:
		models.log_obj_create(user, race.event, models.ACTION_RESULT_CREATE, child_object=result)
	return result

def load_results_for_race(request, event, ak_race_id, ak_distance_raw, race, force_load=False, delete_old_results=True):
	if (not force_load) and (race.loaded != models.RESULTS_NOT_LOADED): # If not force_load, loading only races with no results
		return 0
	if delete_old_results:
		models.Result.objects.filter(race=race).delete()
	results_added = 0
	
	ak_results = models_ak.CUR_AK_RESULT_MODEL.objects.filter(
		ak_race__id=ak_race_id, distance=ak_distance_raw).select_related('ak_person')
	first_name_position = get_first_name_position(ak_results.values_list('name_raw', flat=True))
	for ak_result in ak_results:
		create_result_from_ak(request.user, race, ak_result, first_name_position)
		results_added += 1
	race.loaded = models.LOAD_TYPE_LOADED
	race.loaded_from = "AK55: table {}, RACEID {}".format(models_ak.CUR_AK_RESULT_MODEL._meta.db_table, ak_race_id)
	race.ak_distance_raw = ak_distance_raw
	race.was_checked_for_klb = False
	race.save()
	models.Result.objects.filter(race=race, source=models.RESULT_SOURCE_KLB).delete()
	fill_places(race)
	fill_race_headers(race)
	return results_added

@group_required('admins')
def load_results_from_ak_rezult(request, ak_id=None, race_only_id=None, ak_start="", force=0):
	if ak_id:
		ak_race_ids_to_load = [ak_id]
	else:
		# To load only new RACEID when new version of AK comes
		# ak_race_ids_to_load = sorted(set(models_ak.CUR_AK_RESULT_MODEL.objects.filter(
		# 	ak_race__id__gte=ak_start, is_in_v1=2).order_by('ak_race__id').values_list('ak_race__id', flat=True)))
		# To load only races that recently got their RACEID
		ak_race_ids_to_load = sorted(set(models.Race.objects.exclude(event__ak_race_id='').filter(
			loaded=0).order_by('event__ak_race_id').values_list('event__ak_race_id', flat=True)))
	if race_only_id: # Then we load only results to this race
		race_only = get_object_or_404(models.Race, pk=race_only_id)
	else:
		race_only = None
	#ak_race_ids_to_load = ['TR2014', 'B62010']
	races_added = 0
	results_added = 0
	report = ""
	report_dists = []
	ak_races_loaded = []
	RESULTS_PER_TIME = 10000
	last_ak_race_id = ""
	# We don't delete results from races that we have just filled: there can be different names for distance, e.g. 20км-сокр
	race_ids_in_work = set()

	write_log("\nNew import. Now: " + unicode(datetime.datetime.now()) + "\n")

	for ak_race_id in ak_race_ids_to_load:
		if results_added >= RESULTS_PER_TIME:
			last_ak_race_id = ak_race_id
			break
		events = models.Event.objects.filter(ak_race_id=ak_race_id)
		if events.count() > 1:
			report += write_log(u'Найдено больше одного события с RACEID="{}". Пропускаем.'.format(ak_race_id)) + "<br/>"
			continue
		event = events.first()
		if event is None:
			report += write_log(u'Не найдено событие с RACEID="{}". Пропускаем.'.format(ak_race_id)) + "<br/>"
			continue
		distances_in_races = set(models.Distance.objects.filter(race__event=event).values_list('distance_type', 'length'))
		distances_in_ak_result = set(models_ak.CUR_AK_RESULT_MODEL.objects.filter(
			ak_race__id=ak_race_id).values_list('distance', flat=True))
		distances_absent = []
		for ak_distance_raw in distances_in_ak_result:
			distance = ak_distance_raw.replace(",", ".")
			if distance == u"20 км(2 кр":
				distance = u"20 км"
			if distance == u"20 км-сокр":
				distance = u"20 км"
			if distance == u"21. 0975 к":
				distance = u"21.0975 км"
			if distance == u"21. 1 км":
				distance = u"21.1 км"
			if distance == u"42.195":
				distance = u"42.195 км"
			#res, to_break = process_distance(distance)
			res = distance.strip()
			#if to_break:
			#	distances_absent.append(distance)
			res_split = res.split()
			#if len(res_split) != 2 or models.float_safe(res_split[0]) == 0:
			#	distances_absent.append(distance)
			dist_type, length = pair2type_length(models.float_safe(res_split[0]), res_split[1])
			distance_to_use = None
			if (dist_type, length) in distances_in_races:
				distance_to_use = (dist_type, length)
			elif dist_type == 1 and (42000 <= length <= 42200) and ((1, 42195) in distances_in_races):
				distance_to_use = (1, 42195)
			elif dist_type == 1 and (21000 <= length <= 21100) and ((1, 21098) in distances_in_races):
				distance_to_use = (1, 21098)
			else:
				distances_absent.append(distance)
			if distance_to_use: # models.Distance is found. Let's load results!
				race = models.Race.objects.get(event=event,
					distance=models.Distance.objects.get(distance_type=distance_to_use[0], length=distance_to_use[1]))
				if race_only and (race_only != race):
					continue
				if race.loaded:
					continue
				delete_old_results = race.id not in race_ids_in_work
				n_results = load_results_for_race(request, event, ak_race_id, ak_distance_raw, race, force, delete_old_results)
				if n_results:
					results_added += n_results
					ak_races_loaded.append((ak_race_id, race))
					race_ids_in_work.add(race.id)
		if distances_absent:
			report_dists.append((ak_race_id, event.start_date, event.series.id,
				# ", ".join([unicode(x) for x in distances_in_races_names]),
				", ".join([unicode(x) for x in distances_absent]),
				", ".join([unicode(x) for x in distances_in_ak_result]),
				))
	update_results_count()
	write_log("Import finished. Now: " + str(datetime.datetime.now()) + "\n")
	context = {}
	context['results_added'] = results_added
	context['report'] = report
	context['report_dists'] = report_dists
	context['ak_races_loaded'] = ak_races_loaded
	context['last_ak_race_id'] = last_ak_race_id

	return render(request, "editor/results_import.html", context)

def mark_new_races():
	old_race_ids = set(models_ak.Ak_result.objects.values_list('ak_race__id', flat=True))
	new_race_results = models_ak.Ak_result_v2.objects.exclude(ak_race__id__in=old_race_ids)
	print "Results in new race: {}".format(new_race_results.count())
	new_race_results.update(is_in_v1=2)
	print "Finished!"

def mark_equal_results_in_race(results_v1, results_v2):
	len1 = results_v1.count()
	len2 = results_v2.count()
	n_similar = 0
	if (len1 == 0) or (len2 == 0):
		return
	iter1 = iter2 = 0
	res1 = results_v1[0]
	res2 = results_v2[0]
	while (iter1 < len1) and (iter2 < len2):
		res1 = results_v1[iter1]
		res2 = results_v2[iter2]
		if res1.name_raw > res2.name_raw:
			iter2 += 1
		elif res1.name_raw < res2.name_raw:
			iter1 += 1
		elif res1.bib > res2.bib:
			iter2 += 1
		elif res1.bib < res2.bib:
			iter1 += 1
		elif res1.place > res2.place:
			iter2 += 1
		elif res1.place < res2.place:
			iter1 += 1
		elif res1.time_raw > res2.time_raw:
			iter2 += 1
		elif res1.time_raw < res2.time_raw:
			iter1 += 1
		else:
			similar = True
			if (res1.ak_person and not res2.ak_person) or (res2.ak_person and not res1.ak_person) or (
				res1.ak_person and res2.ak_person and (res1.ak_person.id != res2.ak_person.id) ):
				similar = False
			if similar:
				for field in ['race_date', 'distance', 'result',
					'category', 'place_category', 'birthyear_raw', 'birthday_raw', 'country_raw',
					'city_raw', 'club_raw', 'age_raw', 'comment']:
					if getattr(res1, field) != getattr(res2, field):
						similar = False
						break
			if similar:
				res1.is_in_v2 = 1
				res1.save()
				res2.is_in_v1 = 1
				res2.save()
				n_similar += 1
			iter1 += 1
			iter2 += 1
	return n_similar

def mark_equal_results_in_race_step2():
	race_ids = set(models_ak.Ak_result.objects.filter(is_in_v2=0).values_list('ak_race__id', flat=True))
	race_ids |= set(models_ak.Ak_result_v2.objects.filter(is_in_v1=0).values_list('ak_race__id', flat=True))
	for race_id in race_ids:
		old_results = models_ak.Ak_result.objects.filter(ak_race__id=race_id, is_in_v2=0).order_by('place', 'name_raw')
		new_results = models_ak.Ak_result_v2.objects.filter(ak_race__id=race_id, is_in_v1=0).order_by('place', 'name_raw')
		old_results_num = old_results.count()
		new_results_num = new_results.count()
		if old_results_num == new_results_num:
			print "Race {} with {} results:".format(race_id, old_results.count())
			n_similar = 0
			for i in range(old_results_num):
				print "i={}".format(i)
				old_result = old_results[i]
				new_result = new_results[i]
				similar = True
				if (old_result.ak_person and not new_result.ak_person) or (new_result.ak_person and not old_result.ak_person) or (
					old_result.ak_person and new_result.ak_person and (old_result.ak_person.id != new_result.ak_person.id) ):
					similar = False
				for field in [f.name for f in new_result.__class__._meta.get_fields()]:
					if field not in ['id', 'is_in_v1', 'ak_race', 'ak_person', 'bib']:
				 # ['race_date', 'distance', 'bib', 'time_raw', 'result', 'place',
					# 'category', 'place_category', 'name_raw', 'birthyear_raw', 'birthday_raw', 'country_raw',
					# 'city_raw', 'club_raw', 'age_raw', 'comment']:
						if getattr(old_result, field) != getattr(new_result, field):
							print u"Old id {}, new id {}. Different values for field {}: '{}' != '{}'".format(
								old_result.id, new_result.id, field, getattr(old_result, field), getattr(new_result, field))
							similar = False
							# break
				if similar:
					old_result.is_in_v2 = 1
					old_result.save()
					new_result.is_in_v1 = 1
					new_result.save()
					n_similar += 1
			print "{} similar results".format(n_similar)
	print "Finished!"

def mark_equal_results():
	# old_race_ids = set(models_ak.Ak_result.objects.values_list('ak_race__id', flat=True))
	old_race_ids = ['TN2015', 'ERG15j', 'QC2011']
	print "Number of races to go: {}".format(len(old_race_ids))
	counter = 0
	for race_id in old_race_ids:
		race = models_ak.Ak_race_v2.objects.filter(id=race_id).first()
		if not race:
			continue
		#if race.is_compared_to_v1:
		#	continue
		results_v1 = models_ak.Ak_result.objects.filter(ak_race_id=race_id).order_by('name_raw', 'bib', 'place', 'time_raw')
		results_v2 = models_ak.Ak_result_v2.objects.filter(ak_race_id=race_id).order_by('name_raw', 'bib', 'place', 'time_raw')
		print "Race {}:".format(race_id)
		n_similar = mark_equal_results_in_race(results_v1, results_v2)
		race.is_compared_to_v1 = 1
		race.save()
		print "{} similar results".format(n_similar)
		counter += 1
		if (counter % 500) == 0:
			print "{} races done".format(counter)
	print "Finished!"

def update_field_in_ex_ak_result(ak_result_id, old_ak_result_id, result_id, field_names, ak_field_name):
	ak_result = models_ak.Ak_result_v2.objects.get(id=ak_result_id)
	old_ak_result = models_ak.Ak_result.objects.get(id=old_ak_result_id)
	# race = models.Race.objects.get(id=race_id)
	results = models.Result.objects.filter(id=result_id) #, ak_person=ak_result.ak_person)
	if results.count() > 1:
		print "Found {} results with result_id {}! Stop.".format(result_id)
		return 0
	result = results.first()
	if result is None:
		print "Found no results with result_id {}! Stop.".format(result_id)
		return 0
	for field_name in field_names:
		setattr(result, field_name, getattr(ak_result, ak_field_name))
	result.loaded_from = "AK55: table {}, RACEID {}, result id {}".format(ak_result.__class__._meta.db_table, ak_result.ak_race.id, ak_result.id)
	result.save()
	ak_result.is_in_v1 = 3
	ak_result.save()
	old_ak_result.is_in_v2 = 3
	old_ak_result.save()
	print 'ak_result_v2.id: {}, is_in_v1: {}'.format(ak_result.id, ak_result.is_in_v1)
	print 'ak_result_v1.id: {}, is_in_v2: {}'.format(old_ak_result.id, old_ak_result.is_in_v2)
	print 'Finished!'

def update_manids_for_v2():
	user = User.objects.get(pk=1)
	# race_ids = set(models_ak.Ak_result.objects.filter(is_in_v2=0).values_list('ak_race__id', flat=True))
	# race_ids |= set(models_ak.Ak_result_v2.objects.filter(is_in_v1=0).values_list('ak_race__id', flat=True))
	race_ids = ['MM1984']
	for race_id in race_ids:
		old_results = models_ak.Ak_result.objects.filter(ak_race__id=race_id, is_in_v2=0).order_by('place', 'name_raw')
		new_results = models_ak.Ak_result_v2.objects.filter(ak_race__id=race_id, is_in_v1=0).order_by('place', 'name_raw')
		old_results_num = old_results.count()
		new_results_num = new_results.count()
		if old_results_num == new_results_num:
			print "Race {} with {} results:".format(race_id, old_results_num)
			n_similar = 0
			for i in range(old_results_num):
				print "i={}".format(i)
				old_result = old_results[i]
				new_result = new_results[i]
				similar = True
				for field in [f.name for f in new_result.__class__._meta.get_fields()]:
					if field not in ['id', 'is_in_v1', 'ak_race', 'ak_person', 'bib']:
						if getattr(old_result, field) != getattr(new_result, field):
							print u"Old id {}, new id {}. Different values for field {}: '{}' != '{}'".format(
								old_result.id, new_result.id, field, getattr(old_result, field), getattr(new_result, field))
							similar = False
							# break
				if not similar:
					continue
				if (old_result.ak_person and not new_result.ak_person) or (new_result.ak_person and not old_result.ak_person) or (
					old_result.ak_person and new_result.ak_person and (old_result.ak_person.id != new_result.ak_person.id) ):
					# Everything is similar, ak_persons are different
					# new_ak_person = new_result.ak_person
					# or old_result.ak_person_id
					result_id = models.Result.objects.get(race__event__ak_race_id=new_result.ak_race.id, ak_person__id=new_result.ak_person.id).id
					update_field_in_ex_ak_result(new_result.id, old_result.id, result_id, ['ak_person'], 'ak_person')
					n_similar += 1
			print "{} similar results".format(n_similar)
		elif old_results_num == 0:
			n_results = 0
			print "Race {} with only new {} results:".format(race_id, new_results_num)
			if race_id == 'SAR15f':
				new_race_id = 9243
			elif race_id == 'SAR14c':
				new_race_id = 19727
			elif race_id == 'MM1984':
				new_race_id = 4564
			race = models.Race.objects.get(pk=new_race_id)
			for ak_result in new_results:
				# create_result_from_ak(user, race, ak_result, 1, to_log_action=True)
				ak_result.is_in_v1 = 2
				ak_result.save()
				n_results += 1
			print "{} results were added to race_id {}".format(n_results, new_race_id)
	print "Finished!"

@group_required('admins')
def show_different_results(request):
	race_ids = set(models_ak.Ak_result.objects.filter(is_in_v2=0).values_list('ak_race__id', flat=True))
	race_ids |= set(models_ak.Ak_result_v2.objects.filter(is_in_v1=0).values_list('ak_race__id', flat=True))
	context = {}
	races = []
	for race_id in race_ids:
		old_results = models_ak.Ak_result.objects.filter(ak_race__id=race_id, is_in_v2=0).order_by('place', 'name_raw')
		new_results = models_ak.Ak_result_v2.objects.filter(ak_race__id=race_id, is_in_v1=0).order_by('place', 'name_raw')
		if old_results.count() == new_results.count():
			for i in range(old_results.count()):
				for field in ['race_date', 'distance', 'bib', 'time_raw', 'result', 'place',
					'category', 'place_category', 'name_raw', 'birthyear_raw', 'birthday_raw', 'country_raw',
					'city_raw', 'club_raw', 'age_raw', 'comment']:
					if getattr(old_results[i], field) != getattr(new_results[i], field):
						setattr(old_results[i], field, u'XXX{}'.format(getattr(old_results[i], field)))
						setattr(new_results[i], field, u'XXX{}'.format(getattr(new_results[i], field)))
		races.append({
			'old_results': old_results,
			'new_results': new_results,
			'old_race': models_ak.Ak_race.objects.filter(id=race_id).first(),
			'new_race': models_ak.Ak_race_v2.objects.filter(id=race_id).first(),
			'id': race_id,
			})
	context['races'] = races
	# context['races'] = [{
	# 		'old_results': models_ak.Ak_result.objects.filter(ak_race__id=race_id, is_in_v2=0).order_by('place', 'name_raw'),
	# 		'new_results': models_ak.Ak_result_v2.objects.filter(ak_race__id=race_id, is_in_v1=0).order_by('place', 'name_raw'),
	# 		'old_race': models_ak.Ak_race.objects.filter(id=race_id).first(),
	# 		'new_race': models_ak.Ak_race_v2.objects.filter(id=race_id).first(),
	# 		'id': race_id,
	# 		}
	# 		for race_id in race_ids]
	return render(request, "editor/show_different_results.html", context)
