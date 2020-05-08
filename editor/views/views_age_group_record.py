# -*- coding: utf-8 -*-
from django.db.models import Q, F, ExpressionWrapper, IntegerField
from django.shortcuts import get_object_or_404, render, redirect
from django.template.loader import render_to_string
from django.db.models.functions import ExtractYear
from django.forms import modelformset_factory
from django.contrib import messages
from django.conf import settings
from collections import OrderedDict
import datetime
import io
import os

from results import models, results_util
from results.views.views_common import add_race_dependent_attrs
from editor.forms import RecordResultForm
from editor.views.views_common import group_required
from editor.views.views_stat import set_stat_value
from editor.views.views_user_actions import log_form_change

N_EXTRA_RECORDS = 3

def getRecordResultFormSet(request, user, country=None, gender=None, age_group=None, distance=None, is_indoor=None, add_remaining_cur_leaders=False,
		data=None):
	queryset = models.Record_result.objects.all()
	initial = {}
	initial['created_by'] = user
	# initial['is_from_shatilo'] = True
	initial['was_record_ever'] = True
	initial['cur_place'] = 1
	if country:
		queryset = queryset.filter(country=country)
		initial['country'] = country
	if gender:
		queryset = queryset.filter(gender=gender)
		initial['gender'] = gender
	if age_group:
		queryset = queryset.filter(age_group=age_group)
		initial['age_group'] = age_group
	if distance:
		queryset = queryset.filter(distance=distance)
		initial['distance'] = distance
	if is_indoor is not None:
		queryset = queryset.filter(is_indoor=is_indoor)
		initial['is_indoor'] = is_indoor
	if add_remaining_cur_leaders:
		if age_group: # So the forms must be different only by distance
			existing_distances = set(queryset.values_list('distance_id', flat=True))
			remaining_distances = list(models.Distance.objects.filter(
				pk__in=set(results_util.DISTANCES_FOR_COUNTRY_RECORDS) - existing_distances).order_by(
				'distance_type', '-length'))
			initials = [dict(initial) for _ in range(len(remaining_distances))]
			for i, distance in enumerate(remaining_distances):
				initials[i]['distance'] = distance
		else: # So the forms must be different only by age group
			existing_age_groups = set(queryset.values_list('age_group__id', flat=True))
			remaining_age_groups = list(models.Record_age_group.objects.exclude(pk__in=existing_age_groups))
			initials = [dict(initial) for _ in range(len(remaining_age_groups))]
			for i, age_group in enumerate(remaining_age_groups):
				initials[i]['age_group'] = age_group
	else:
		initials = [initial] * N_EXTRA_RECORDS
	RaceFormSet = modelformset_factory(models.Record_result, form=RecordResultForm, can_delete=True, extra=len(initials))
	return RaceFormSet(
		data=data,
		queryset=queryset,
		initial=initials,
		form_kwargs={'distance_type': models.TYPE_MINUTES if (distance and (distance.distance_type == models.TYPE_MINUTES)) else models.TYPE_METERS},
	)

@group_required('admins')
def age_group_records_edit(request, country_id=None, gender_code=None, distance_code=None, is_indoor=None, age=None):
	context = {}
	user = request.user

	country = get_object_or_404(models.Country, pk=(country_id if country_id else 'RU'))
	is_indoor = (results_util.int_safe(is_indoor) > 0)
	gender = results_util.GENDER_CODES_INV.get(gender_code) if gender_code else models.GENDER_MALE
	if not gender:
		raise Http404()

	formset_params = {}
	formset_params['country'] = country
	formset_params['is_indoor'] = is_indoor
	formset_params['gender'] = gender

	distance = None
	if distance_code:
		distance_id = results_util.DISTANCE_CODES_INV.get(distance_code)
		distance = get_object_or_404(models.Distance, pk=distance_id, pk__in=results_util.DISTANCES_FOR_COUNTRY_RECORDS)
		formset_params['distance'] = distance
	if age is not None:
		age = results_util.int_safe(age)
		age_group = get_object_or_404(models.Record_age_group, age_min=age if age else None)
		formset_params['age_group'] = age_group
	formset_params['add_remaining_cur_leaders'] = (distance is not None) or (age is not None)

	if 'btnSubmitRecords' in request.POST:
		formset = getRecordResultFormSet(request, user, data=request.POST, **formset_params)
		if formset.is_valid():
			formset.save()
			for record in formset.new_objects:
				record.fill_and_save_if_needed()
			for record, changed_data in formset.changed_objects:
				record.fill_and_save_if_needed()

			messages.success(request, (u'{} рекордов добавлено, {} обновлено, {} удалено').format(
				len(formset.new_objects), len(formset.changed_objects), len(formset.deleted_objects)))
			return redirect('results:age_group_records')
		else:
			messages.warning(request, u'Рекорды не сохранены. Пожалуйста, исправьте ошибки в форме')
			context['errors'] = unicode(formset.errors) # TODO: REMOVE
	else:
		formset = getRecordResultFormSet(request, user, **formset_params)

	if age == 0:
		context['page_title'] = u'Редактирование абсолютных рекордов {}{} у {}'.format(
			formset_params['country'].prep_case, u' в закрытых помещениях' if is_indoor else u'',
			u'мужчин' if (gender == models.GENDER_MALE) else u'женщин')
	else:
		context['page_title'] = u'Редактирование рекордов в возрастных группах'
	context['formset'] = formset
	return render(request, 'editor/age_groups/age_group_records_edit.html', context)

@group_required('admins')
def age_group_record_details(request, record_result_id=None):
	context = {}

	if record_result_id:
		record = get_object_or_404(models.Record_result, pk=record_result_id)
		if record.result_id:
			messages.warning(request, u'Рекорд {} привязан к результату с id {}. Такие редактировать незачем'.format(record, record.result_id))
			return redirect(record.get_group_url())
		create_new = False
	else:
		record = models.Record_result()
		create_new = True

	frmRecord = None
	distance_type = models.TYPE_METERS # FIXME
	if 'btnSubmitRecord' in request.POST:
		frmRecord = RecordResultForm(request.POST, instance=record, distance_type=distance_type)
		if frmRecord.is_valid():
			record = frmRecord.save()
			log_form_change(request.user, frmRecord, action=models.ACTION_CREATE if create_new else models.ACTION_UPDATE)
			record.fill_and_save_if_needed()
			messages.success(request, u'Рекорд «{}» успешно {}'.format(record, u'создан' if create_new else u'обновлён'))
			return redirect(record.get_group_url())
		else:
			messages.warning(request, u'Рекорд не {}. Пожалуйста, исправьте ошибки в форме.'.format(u'создан' if create_new else u'обновлён'))
			context['errors'] = unicode(form.errors) # TODO: REMOVE

	if frmRecord is None:
		frmRecord = RecordResultForm(instance=record, distance_type=distance_type)
	context['record'] = record
	context['form'] = frmRecord
	context['page_title'] = u'Рекорд {} (id {})'.format(record, record.id) if record.id else u'Добавление нового рекорда'
	return render(request, 'editor/age_groups/age_group_record_details.html', context)

@group_required('admins')
def age_group_record_delete(request, record_result_id):
	if 'btnDeleteRecord' in request.POST:
		record_result = get_object_or_404(models.Record_result, pk=record_result_id)
		result_id = record_result.result_id
		if result_id:
			country = record_result.country
			gender = record_result.gender
			age_group = record_result.age_group
			distance = record_result.distance
			is_indoor = record_result.is_indoor
			record_result.delete()
			update_records_for_given_tuple(country, gender, age_group, distance, is_indoor)
			models.Result_not_for_age_group_record.objects.get_or_create(country=country, age_group=age_group, result_id=result_id)
			messages.success(request, u'Результат с id {} удалён из рекордов'.format(result_id))
		else:
			messages.warning(request, u'Рекордный результат с id {} не может быть удалён — он не привязан ни к какому результату'.format(record_result_id))
		return redirect('results:age_group_record_details',
			country_id=record_result.country_id,
			gender_code=results_util.GENDER_CODES[record_result.gender],
			age=record_result.age_group.age_min if record_result.age_group.age_min else 0,
			distance_code=results_util.DISTANCE_CODES[record_result.distance_id],
			is_indoor=1 if record_result.is_indoor else 0,
		)
	return redirect('results:age_group_records')

def create_age_groups():
	# for age in range(35, 105, 5):
	# 	models.Record_age_group.objects.create(age_min=age)
	# models.Record_age_group.objects.create(age_min=0)
	# for age in (18, 20, 23):
	# 	models.Record_age_group.objects.create(age_min=age, age_group_type=models.RECORD_AGE_GROUP_TYPE_YOUNG)
	models.Record_age_group.objects.filter(age_min=0).update(age_min=None)
	models.Record_age_group.objects.filter(age_min=None).update(age_group_type=models.RECORD_AGE_GROUP_TYPE_ABSOLUTE)
	print 'Total number of groups:', models.Record_age_group.objects.all().count()

def get_appropriate_results(country, gender, age_group, distance, is_indoor):
	other_gender = 3 - gender
	results = models.Result.objects.filter(
			Q(race__distance_real=None) | Q(race__distance_real__length__gte=distance.length),
			Q(runner=None) | Q(runner__city=None) | Q(runner__city__region__country=country),
			race__distance=distance,
			status=models.STATUS_FINISHED,
			race__is_for_handicapped=False,
			race__event__start_date__year__gte=1991,
		).exclude(runner__gender=other_gender).exclude(gender=other_gender).annotate(
		res_diff=ExpressionWrapper(ExtractYear(F('race__event__start_date'))-ExtractYear(F('birthday')), output_field=IntegerField())).annotate(
		runner_diff=ExpressionWrapper(ExtractYear(F('race__event__start_date'))-ExtractYear(F('runner__birthday')), output_field=IntegerField()))
	if country.id != 'RU': # For other countries, either runner or event must belong to the country
		results = results.filter(
			Q(runner__city__region__country=country)
			| Q(race__event__city__region__country=country)
			| Q(race__event__series__city__region__country=country)
		)

	if age_group.age_group_type == models.RECORD_AGE_GROUP_TYPE_SENIOR:
		age_min = age_group.age_min
		age_max = age_min + models.AGE_GROUP_RECORDS_AGE_GAP
		results = results.exclude(
			Q(age__lt=age_min) | Q(age__gt=age_max)).exclude(
			Q(res_diff__lt=age_min) | Q(res_diff__gt=age_max), birthday__isnull=False).exclude(
			Q(runner_diff__lt=age_min) | Q(runner_diff__gt=age_max), runner__isnull=False, runner__birthday__isnull=False).exclude(
			Q(runner=None) | Q(runner__birthday=None), age=None, birthday=None)
	elif age_group.age_group_type == models.RECORD_AGE_GROUP_TYPE_YOUNG:
		results = results.exclude(age__gt=age_group.age_min).exclude(res_diff__gt=age_group.age_min).exclude(
			runner__isnull=False, runner__birthday__isnull=False, runner_diff__gt=age_group.age_min).exclude(
			Q(runner=None) | Q(runner__birthday=None), age=None, birthday=None)

	if is_indoor:
		results = results.filter(Q(race__surface_type=models.SURFACE_INDOOR)
			| Q(race__surface_type=models.SURFACE_DEFAULT, race__event__surface_type=models.SURFACE_INDOOR)
			| Q(race__surface_type=models.SURFACE_DEFAULT, race__event__surface_type=models.SURFACE_DEFAULT,
			 	race__event__series__surface_type=models.SURFACE_INDOOR)
			)
	else:
		hard_surfaces = set([models.SURFACE_ROAD, models.SURFACE_STADIUM, models.SURFACE_HARD])
		results = results.filter(Q(race__surface_type__in=hard_surfaces)
			| Q(race__surface_type=models.SURFACE_DEFAULT, race__event__surface_type__in=hard_surfaces)
			| Q(race__surface_type=models.SURFACE_DEFAULT, race__event__surface_type=models.SURFACE_DEFAULT,
			 	race__event__series__surface_type__in=hard_surfaces | set([models.SURFACE_DEFAULT]))
			)
	return results

# Returns pairs: (result, age_on_event_date if known else None)
# Finds <=3 filtered results whose id's don't belong to bad_record_result_ids
def filter_by_age_on_event_date(results, age_group, bad_record_result_ids, debug=False):
	filtered_results = []
	n_good_results = 0
	age_min = age_group.age_min
	for result in results:
		if debug >= 2:
			print 'Event: {} Date: {} Result: {}'.format(result.race.event, result.race.event.start_date, result)
			if result.runner:
				print 'Runner: {} Birthday: {}'.format(result.runner, result.runner.strBirthday())
		if result.runner and result.runner.birthday_known:
			result_is_good = False
			age_on_event_date = result.race.event.get_age_on_event_date(result.runner.birthday)
			if age_group.age_group_type == models.RECORD_AGE_GROUP_TYPE_ABSOLUTE:
				result_is_good = True
			elif age_group.age_group_type == models.RECORD_AGE_GROUP_TYPE_SENIOR:
				if debug >= 2:
					print 'age_on_event_date: {}'.format(age_on_event_date)
				result_is_good = (age_min <= age_on_event_date < (age_min + models.AGE_GROUP_RECORDS_AGE_GAP))
			else: # age_group.age_group_type == models.RECORD_AGE_GROUP_TYPE_YOUNG
				# We can check this even only if result.runner.birthday.year is known, but we have very vew runners with only birthyear
				result_is_good = ((result.race.event.start_date.year - result.runner.birthday.year) < age_min)

			if result_is_good:
				filtered_results.append((result, age_on_event_date))
				if result.id not in bad_record_result_ids:
					n_good_results += 1
				if debug >= 2:
					print 'Appending!'
			else:
				if debug >= 2:
					print 'Bad age_on_event_date!'
		else:
			filtered_results.append((result, None))
			if result.id not in bad_record_result_ids:
				n_good_results += 1
			if debug >= 2:
				print 'No age_on_event_date. Appending!'
		if n_good_results >= 3:
			break
	return filtered_results

def get_bad_result_ids_by_age_group(country, age_groups):
	all_bad_results = country.result_not_for_age_group_record_set
	bad_result_ids_by_age_group = {}
	for age_group in age_groups:
		bad_result_ids_by_age_group[age_group] = set(all_bad_results.filter(age_group=age_group).values_list('result_id', flat=True))
	return bad_result_ids_by_age_group

def find_better_age_group_results_for_tuple(country, gender, age_group, distance, is_indoor, bad_result_ids, debug=False):
	n_results_created = 0
	distance_is_minutes = (distance.distance_type == models.TYPE_MINUTES)
	result_order = '-result' if distance_is_minutes else 'result'
	existing_record_result_ids = set(age_group.record_result_set.filter(country=country, gender=gender, distance=distance,
		is_indoor=is_indoor).exclude(result=None).values_list('result_id', flat=True))
	appropriate_results = get_appropriate_results(country, gender, age_group, distance, is_indoor).exclude(
		pk__in=existing_record_result_ids).select_related('race__event', 'runner')
	
	# We take 3rd result ever (with cur_place=3) if it exists
	worst_record_result = age_group.record_result_set.filter(country=country, gender=gender, distance=distance, is_indoor=is_indoor).exclude(
		cur_place=None).order_by('-cur_place').first()
	if worst_record_result:
		# E.g., if we already have two saved results, we need only one result slower than current with cur_place=2
		n_slower_results_needed = 3 - worst_record_result.cur_place
		if debug >= 2:
			print 'Worst record result: {} (id {}, place {})'.format(worst_record_result,
				worst_record_result.result.id if worst_record_result.result else 'None', worst_record_result.cur_place)

	best_results_with_ages = filter_by_age_on_event_date(appropriate_results.order_by(result_order)[:20], age_group, bad_result_ids, debug)
	n_slower_results_found = 0
	for result, age_on_event_date in best_results_with_ages:
		if worst_record_result:
			result_is_slower_than_worst = (result.result < worst_record_result.value) if distance_is_minutes else \
				(result.result > worst_record_result.value)
			if result_is_slower_than_worst:
				n_slower_results_found += 1
				if n_slower_results_found > n_slower_results_needed:
					break
		models.Possible_record_result.objects.create(
				country=country,
				gender=gender,
				age_group=age_group,
				age_on_event_date=age_on_event_date,
				distance=distance,
				is_indoor=is_indoor,
				result=result,
			)
		existing_record_result_ids.add(result.id)
		n_results_created += 1

	# Also we find possible previous records
	for prev_record_result in age_group.record_result_set.filter(country=country, gender=gender, distance=distance, is_indoor=is_indoor,
			was_record_ever=True).exclude(race=None):
		results = appropriate_results.filter(race__event__start_date__lt=prev_record_result.date)
		results = results.filter(result__gt=prev_record_result.value) if distance_is_minutes else \
			results.filter(result__lt=prev_record_result.value)
		best_results_with_ages = filter_by_age_on_event_date(results.order_by(result_order)[:20], age_group, bad_result_ids, debug)
		if best_results_with_ages:
			result, age_on_event_date = best_results_with_ages[0]
			if result.id not in existing_record_result_ids:
				models.Possible_record_result.objects.create(
						country=country,
						gender=gender,
						age_group=age_group,
						age_on_event_date=age_on_event_date,
						distance=distance,
						is_indoor=is_indoor,
						result=result,
						can_be_prev_record=True,
					)
				existing_record_result_ids.add(result.id)
				n_results_created += 1
	return n_results_created

@group_required('admins')
def generate_better_age_group_results_for_tuple(request, country_id, gender_code, age, distance_code, is_indoor):
	country = models.Country.objects.get(pk=country_id)
	gender = results_util.GENDER_CODES_INV.get(gender_code)
	if not gender:
		raise Http404()
	age_min = None if (age == '0') else age
	age_group = get_object_or_404(models.Record_age_group, age_min=age_min)
	distance_id = results_util.DISTANCE_CODES_INV.get(distance_code)
	distance = get_object_or_404(models.Distance, pk=distance_id, pk__in=results_util.DISTANCES_FOR_COUNTRY_RECORDS)
	is_indoor = (is_indoor == '1')

	n_results_deleted = age_group.possible_record_result_set.filter(country=country, gender=gender, distance_id=distance_id, is_indoor=is_indoor).delete()
	update_records_for_given_tuple(country, gender, age_group, distance, is_indoor)

	bad_result_ids = set(country.result_not_for_age_group_record_set.filter(age_group=age_group).values_list('result_id', flat=True))
	n_results_created = find_better_age_group_results_for_tuple(country, gender, age_group, distance, is_indoor, bad_result_ids, debug=False)

	messages.success(request, u'Удалено возможных рекордов: {}, найдено возможных рекордов: {}'.format(n_results_deleted, n_results_created))
	return redirect('results:age_group_record_details', country_id=country_id, gender_code=gender_code, age=age, distance_code=distance_code,
		is_indoor=1 if is_indoor else 0)

def generate_better_age_group_results(country_id, debug=False):
	if debug:
		print '{} generate_better_age_group_results for country {} started'.format(datetime.datetime.now(), country_id)
	country = models.Country.objects.get(pk=country_id)
	is_indoor = False
	models.Possible_record_result.objects.filter(country=country, is_indoor=is_indoor).delete()

	distances = [models.Distance.objects.get(pk=dist_id) for dist_id in results_util.DISTANCES_FOR_COUNTRY_RECORDS]

	age_groups = models.Record_age_group.objects.exclude(age_group_type=models.RECORD_AGE_GROUP_TYPE_YOUNG).order_by('age_min')
	bad_result_ids_by_age_group = get_bad_result_ids_by_age_group(country, age_groups)
	n_results_created = 0

	for gender in (models.GENDER_MALE, models.GENDER_FEMALE):
		for distance in distances:
	# for gender in (models.GENDER_MALE, ):
	# 	for distance in [models.Distance.objects.get(pk=results_util.DIST_200M_ID)]:
			distance_is_minutes = (distance.distance_type == models.TYPE_MINUTES)
			result_order = '-result' if distance_is_minutes else 'result'
			for age_group in age_groups:
			# for age_group in models.Record_age_group.objects.filter(age_min=75).order_by('age_min'):
				# if debug:
				# 	print results_util.GENDER_CHOICES[gender][1], distance, age_group
				update_records_for_given_tuple(country, gender, age_group, distance, is_indoor)
				n_results_created += find_better_age_group_results_for_tuple(
					country, gender, age_group, distance, is_indoor, bad_result_ids_by_age_group[age_group], debug)

	set_stat_value('possible_age_records_generated', 0, datetime.date.today())
	if debug:
		print '{} generate_better_age_group_results for country {} finished'.format(datetime.datetime.now(), country_id)
	print 'Results created:', n_results_created

@group_required('admins')
def better_age_group_results(request, country_id='RU', hide_bad_results=True):
	country = models.Country.objects.get(pk=country_id)
	is_indoor = False

	context = {}
	context['last_update'] = models.Statistics.objects.filter(name='possible_age_records_generated').order_by('-date_added').first().date_added
	context['page_title'] = u'Возможные результаты в возрастных группах лучше официальных рекордов {}'.format(country.prep_case)
	if not hide_bad_results:
		context['page_title'] += u', включая помеченные плохими'
	context['country'] = country
	context['to_show_buttons'] = True
	context['hide_bad_results'] = hide_bad_results

	# TODO: add other age groups
	age_groups = models.Record_age_group.objects.exclude(age_group_type=models.RECORD_AGE_GROUP_TYPE_YOUNG).order_by('age_min')
	bad_result_ids_by_age_group = get_bad_result_ids_by_age_group(country, age_groups)
	
	distances = [models.Distance.objects.get(pk=dist_id) for dist_id in results_util.DISTANCES_FOR_COUNTRY_RECORDS]

	context['items'] = []
	for gender in (models.GENDER_MALE, models.GENDER_FEMALE):
		for distance in distances:
			for age_group in age_groups:
				data = {}
				data['best_results'] = age_group.possible_record_result_set.filter(country=country, gender=gender, distance=distance,
					is_indoor=is_indoor).select_related('result__race__event__series__city__region__country', 'result__race__event__city__region__country',
					'result__runner__user__user_profile', 'result__runner__city__region__country', 'result__result_on_strava',
					'result__category_size').order_by('result__result')
				data['bad_results'] = bad_result_ids_by_age_group[age_group]
				if hide_bad_results:
					data['best_results'] = data['best_results'].exclude(result_id__in=data['bad_results'])

				data['record_results'] = age_group.record_result_set.filter(country=country, gender=gender, distance=distance, is_indoor=is_indoor,
					cur_place__gte=1).select_related('result__race__event__series', 'result__runner__user__user_profile').order_by('cur_place')
				if data['best_results'].exists():
					data['gender_name'] = models.GENDER_CHOICES[gender][1]
					data['age_group'] = age_group
					data['distance'] = distance
					context['items'].append(data)
	return render(request, 'editor/age_groups/better_age_group_results.html', context)

@group_required('admins')
def mark_possible_age_group_record_as_bad(request, country_id, age_group_id):
	country = get_object_or_404(models.Country, pk=country_id)
	age_group = get_object_or_404(models.Record_age_group, pk=age_group_id)
	if 'result_id' in request.POST:
		result = get_object_or_404(models.Result, pk=request.POST['result_id'])
		if models.Result_not_for_age_group_record.objects.filter(country=country, age_group=age_group, result=result).exists():
			messages.warning(request, u'Результат с id {} уже был помечен как негодный для страны {} и возрастной группы {}'.format(
				result.id, country, age_group))
		else:
			models.Result_not_for_age_group_record.objects.create(country=country, age_group=age_group, result=result)
			messages.success(request, u'Результат с id {} помечен как негодный'.format(result.id))
	return redirect('editor:better_age_group_results')

@group_required('admins')
def mark_possible_age_group_record_as_good(request, country_id, age_group_id):
	country = get_object_or_404(models.Country, pk=country_id)
	age_group = get_object_or_404(models.Record_age_group, pk=age_group_id)
	if 'result_id' in request.POST:
		result = get_object_or_404(models.Result, pk=request.POST['result_id'])
		result_not_for_age_group_record = models.Result_not_for_age_group_record.objects.filter(country=country, age_group=age_group, result=result).first()
		if result_not_for_age_group_record:
			result_not_for_age_group_record.delete()
			messages.success(request, u'Результат с id {} помечен как хороший'.format(result.id))
		else:
			messages.warning(request, u'Результат с id {} и так считается хорошим для страны {} и возрастной группы {}'.format(
				result.id, country, age_group))
	return redirect('editor:better_age_group_results')

def get_record_before_given_if_exists(records, value_order, given_record):
	return records.filter(date__lt=given_record.date).order_by(value_order, 'date').first()

# Mark current top-3 results and results that were records ever
def update_records_for_given_tuple(country, gender, age_group, distance, is_indoor):
	records = age_group.record_result_set.filter(country=country, gender=gender, distance=distance, is_indoor=is_indoor)
	records.update(cur_place=None, was_record_ever=False)

	distance_is_minutes = (distance.distance_type == models.TYPE_MINUTES)
	value_order = '-value' if distance_is_minutes else 'value'
	cur_record = None
	for i, record in enumerate(records.order_by(value_order, 'date')[:3]):
		record.cur_place = i + 1
		record.save()
		if i == 0:
			cur_record = record
	if cur_record: # So we have at least one record result
		prev_record = get_record_before_given_if_exists(records, value_order, cur_record)
		while prev_record:
			prev_record.was_record_ever = True
			prev_record.save()
			prev_record = get_record_before_given_if_exists(records, value_order, prev_record)

def update_all_tuples():
	tuples = set()
	for record_result in models.Record_result.objects.all().select_related('age_group', 'country', 'distance'):
		tuples.add((record_result.country, record_result.gender, record_result.age_group, record_result.distance, record_result.is_indoor))
	print len(tuples), 'tuples'
	for t in tuples:
		update_records_for_given_tuple(*t)
	print models.Record_result.objects.filter(was_record_ever=True).count()

@group_required('admins')
def add_possible_age_group_records(request):
	if request.method == 'POST':
		n_records_added = 0
		tuples_with_changed_records = set()
		for key, val in request.POST.items():
			if key.startswith("possible_result_"):
				possible_record_result_id = results_util.int_safe(key[len("possible_result_"):])
				possible_record_result = models.Possible_record_result.objects.filter(pk=possible_record_result_id).first()
				if possible_record_result is None:
					messages.warning(request, u'Возможный рекорд с id {} не найден'.format(possible_record_result_id))
				elif models.Result_not_for_age_group_record.objects.filter(country_id=possible_record_result.country_id,
						age_group_id=possible_record_result.age_group_id, result_id=possible_record_result.result_id).exists():
					messages.warning(request, u'Возможный рекорд с id {} помечен как плохой. Не добавляем в рекорды'.format(possible_record_result.id))
				elif models.Record_result.objects.filter(country_id=possible_record_result.country_id,
						age_group_id=possible_record_result.age_group_id, result_id=possible_record_result.result_id).exists():
					messages.warning(request, u'Возможный рекорд с id {} уже и так числится в рекордах. Удаляем с этой страницы'.format(
						possible_record_result.id))
					possible_record_result.delete()
				else:
					record_result = models.Record_result.objects.create(
							country_id=possible_record_result.country_id,
							gender=possible_record_result.gender,
							age_group_id=possible_record_result.age_group_id,
							age_on_event_date=possible_record_result.age_on_event_date,
							distance_id=possible_record_result.distance_id,
							is_indoor=possible_record_result.is_indoor,
							value=possible_record_result.result.result,
							runner=possible_record_result.result.runner,
							result=possible_record_result.result,
							race=possible_record_result.result.race,
							created_by=request.user,
						)
					record_result.fill_and_save_if_needed()
					n_records_added += 1
					tuples_with_changed_records.add((record_result.country, record_result.gender, record_result.age_group, record_result.distance,
						record_result.is_indoor))
					possible_record_result.delete()
		for tup in tuples_with_changed_records:
			update_records_for_given_tuple(*tup)
		if n_records_added > 0:
			messages.success(request, u'Добавлено результатов в рекорды в возрастных группах: {}'.format(n_records_added))
	return redirect('editor:better_age_group_results')

@group_required('admins')
def update_age_group_records(request, country_id=None, gender_code=None, age=None, distance_code=None, is_indoor=None):
	gender = results_util.GENDER_CODES_INV.get(gender_code)
	if not gender:
		raise Http404()
	age_min = None if (age == '0') else age
	age_group = get_object_or_404(models.Record_age_group, age_min=age_min)
	distance_id = results_util.DISTANCE_CODES_INV.get(distance_code)
	is_indoor = (is_indoor == '1')

	n_updated = 0
	for record in age_group.record_result_set.filter(country_id=country_id, gender=gender, distance_id=distance_id, is_indoor=is_indoor):
		n_updated += record.fill_and_save_if_needed()
	messages.success(request, u'Уточнена информация о рекордах: {}'.format(n_updated))
	return redirect('results:age_group_record_details', country_id=country_id, gender_code=gender_code, age=age, distance_code=distance_code,
		is_indoor=1 if is_indoor else 0)

def update_records_once():
	n_updated = 0
	for record in models.Record_result.objects.all():
		n_updated += record.fill_and_save_if_needed()
	print 'Updated:', n_updated
