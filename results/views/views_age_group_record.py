# -*- coding: utf-8 -*-
from django.shortcuts import get_object_or_404, render, redirect, reverse
from django.db.models import Q
from django.http import Http404

from collections import OrderedDict
import datetime

from results import models, forms, results_util
from results.views.views_common import user_edit_vars

distances = [models.Distance.objects.get(pk=dist_id) for dist_id in results_util.DISTANCES_FOR_COUNTRY_RECORDS]

def age_group_records(request, country_id='RU'):
	context = user_edit_vars(request.user)
	context['country'] = get_object_or_404(models.Country, pk=country_id, pk__in=results_util.THREE_COUNTRY_IDS)
	context['page_title'] = u'Рекорды {} в беге в возрастных группах'.format(context['country'].prep_case)
	context['is_indoor'] = 0
	
	distances_to_use = distances if context['is_admin'] else distances[:1] + distances[3:]
	context['distances_and_codes'] = [(distance, results_util.DISTANCE_CODES[distance.id]) for distance in distances_to_use]
	age_groups = models.Record_age_group.objects.all()
	if not context['is_admin']:
		age_groups = age_groups.exclude(age_group_type=models.RECORD_AGE_GROUP_TYPE_YOUNG)

	data = OrderedDict([
			(models.GENDER_MALE, {'name': u'Мужчины', 'gender_code': results_util.GENDER_CODES[models.GENDER_MALE],
				'age_groups': OrderedDict()}),
			(models.GENDER_FEMALE, {'name': u'Женщины', 'gender_code': results_util.GENDER_CODES[models.GENDER_FEMALE],
				'age_groups': OrderedDict()})
		])
	for age_group in age_groups:
		for gender in [models.GENDER_MALE, models.GENDER_FEMALE]:
			data[gender]['age_groups'][age_group] = OrderedDict([(distance, None) for distance in distances_to_use])

	for record_result in models.Record_result.objects.filter(
				country_id=context['country'].id,
				is_indoor=context['is_indoor'],
				age_group__in=age_groups,
				distance__in=distances_to_use,
				cur_place=1,
			).select_related(
			'age_group', 'distance', 'runner__user__user_profile', 'result__race__distance'):
		data[record_result.gender]['age_groups'][record_result.age_group][record_result.distance] = record_result

	context['data'] = data

	return render(request, 'age_group_records/age_group_records.html', context)

def age_group_details(request, country_id=None, gender_code=None, age=None, distance_code=None, is_indoor=None):
	if request.method == 'POST':
		return redirect('results:age_group_record_details',
			country_id=request.POST.get('country_id', 'RU'),
			gender_code=results_util.GENDER_CODES[results_util.int_safe(request.POST.get('gender', models.GENDER_MALE))],
			age=request.POST.get('age', 0),
			distance_code=results_util.DISTANCE_CODES[results_util.int_safe(request.POST.get('distance_id', results_util.DIST_MARATHON_ID))],
			is_indoor=request.POST.get('is_indoor', 0),
		)

	country = get_object_or_404(models.Country, pk=country_id, pk__in=results_util.THREE_COUNTRY_IDS)
	gender = results_util.GENDER_CODES_INV.get(gender_code)
	if not gender:
		raise Http404()
	age_min = None if (age == '0') else age
	age_group = get_object_or_404(models.Record_age_group, age_min=age_min)

	distance_id = results_util.DISTANCE_CODES_INV.get(distance_code)
	distance = get_object_or_404(models.Distance, pk=distance_id, pk__in=results_util.DISTANCES_FOR_COUNTRY_RECORDS)
	is_indoor = (is_indoor == '1')

	context = user_edit_vars(request.user)
	context['country'] = country
	context['form'] = forms.AgeGroupRecordForm(initial={
			'country_id': country.id,
			'distance_id': distance.id,
			'gender': gender,
			'age': age_group.age_min if age_group.age_min else 0,
		})

	records = age_group.record_result_set.filter(country=country, gender=gender, distance=distance, is_indoor=is_indoor).select_related(
		'result__race__event__series__city__region__country', 'result__race__event__city__region__country',
		'result__runner__user__user_profile', 'result__runner__city__region__country', 'result__result_on_strava')
	context['results_best_overall'] = records.exclude(cur_place=None).order_by('cur_place')
	context['old_records'] = records.filter(was_record_ever=True).exclude(cur_place=1).order_by('-date')

	context['has_shatilo_results'] = context['results_best_overall'].filter(is_from_shatilo=True).exists() \
		or context['old_records'].filter(is_from_shatilo=True).exists()

	if context['is_admin']:
		context['other_results'] = records.filter(was_record_ever=False, cur_place=None).order_by('-result__race__event__start_date')
		context['has_shatilo_results'] = context['has_shatilo_results'] or context['other_results'].filter(is_from_shatilo=True).exists()
		context['update_records_link'] = reverse('editor:update_age_group_records', kwargs={'country_id': country_id, 'gender_code': gender_code,
			'age': age, 'distance_code': distance_code, 'is_indoor': 1 if is_indoor else 0})
		context['generate_records_link'] = reverse('editor:generate_better_age_group_results_for_tuple',
			kwargs={'country_id': country_id, 'gender_code': gender_code,
				'age': age, 'distance_code': distance_code, 'is_indoor': 1 if is_indoor else 0})

	context['page_title_first'] = u'Рекорды {}'.format(country.prep_case)
	context['page_title_second'] = u'{} на дистанции {}{}'.format(
			age_group.get_full_name_in_prep_case(gender),
			distance.name,
			u' в закрытых помещениях' if is_indoor else '',
		)
	context['page_title'] = context['page_title_first'] + context['page_title_second']
	return render(request, 'age_group_records/age_group_details.html', context)

def records_better_than_shatilo(request):
	context = user_edit_vars(request.user)
	context['page_title'] = u'Результаты в базе ПроБЕГа лучше рекордов России из файла Анатолия Шатило'
	distances = [models.Distance.objects.get(pk=dist_id) for dist_id in results_util.DISTANCES_FOR_COUNTRY_RECORDS
		if dist_id not in (results_util.DIST_1HOUR_ID, results_util.DIST_HALFMARATHON_ID)]
	country = models.Country.objects.get(pk='RU')
	is_indoor = 0

	context['items'] = []
	context['n_better_records'] = 0
	for gender in (models.GENDER_MALE, models.GENDER_FEMALE):
		for distance in distances:
			for age_group in models.Record_age_group.objects.filter(age_group_type=models.RECORD_AGE_GROUP_TYPE_SENIOR).order_by('age_min'):
				data = {}
				records = age_group.record_result_set.filter(country=country, gender=gender, distance=distance, is_indoor=is_indoor)
				data['better_records'] = records.filter(Q(cur_place=1) | Q(was_record_ever=True), is_from_shatilo=False).select_related(
					'result__race__event__series__city__region__country', 'result__race__event__city__region__country',
					'result__runner__user__user_profile', 'result__runner__city__region__country', 'result__result_on_strava',
					'result__category_size').order_by('result__result')
				n_records = data['better_records'].count()
				if n_records > 0:
					context['n_better_records'] += n_records
					data['shatilo_record'] = records.filter(is_from_shatilo=True).first()
					data['gender_name'] = models.GENDER_CHOICES[gender][1]
					data['age_group'] = age_group
					data['distance'] = distance
					context['items'].append(data)
	return render(request, 'age_group_records/records_better_than_shatilo.html', context)

def records_for_distance(request, country_id, distance_code, is_indoor=False):
	if request.method == 'POST':
		kwargs = {}
		if is_indoor:
			kwargs['is_indoor'] = 1
		return redirect('results:age_group_records_for_distance',
			country_id=request.POST.get('country_id', 'RU'),
			distance_code=results_util.DISTANCE_CODES[results_util.int_safe(request.POST.get('distance_id', results_util.DIST_MARATHON_ID))],
			**kwargs
		)

	country = get_object_or_404(models.Country, pk=country_id, pk__in=results_util.THREE_COUNTRY_IDS)
	distance_id = results_util.DISTANCE_CODES_INV.get(distance_code)
	distance = get_object_or_404(models.Distance, pk=distance_id, pk__in=results_util.DISTANCES_FOR_COUNTRY_RECORDS)
	is_indoor = (is_indoor == '1')

	context = user_edit_vars(request.user)
	distance_name = u'марафоне'
	context['page_title_first'] = u'Рекорды в возрастных группах в {}'.format(country.prep_case)
	context['page_title_second'] = u': {}{}'.format(distance.name, u' в закрытых помещениях' if is_indoor else '')
	context['page_title'] = context['page_title_first'] + context['page_title_second']
	context['country'] = country

	context['form'] = forms.AgeGroupRecordsForDistanceForm(initial={
			'country_id': country.id,
			'distance_id': distance.id,
		})

	data = OrderedDict()
	for age_group in models.Record_age_group.objects.exclude(age_group_type=models.RECORD_AGE_GROUP_TYPE_YOUNG).order_by('age_min'):
		data[age_group] = {}

	records = country.record_result_set.filter(distance=distance, is_indoor=is_indoor, cur_place=1).exclude(
		age_group__age_group_type=models.RECORD_AGE_GROUP_TYPE_YOUNG).select_related(
		'result__race__event__series__city__region__country', 'result__race__event__city__region__country',
		'result__runner__user__user_profile', 'result__runner__city__region__country').order_by('age_group__age_min')
	for record in records:
		data[record.age_group][record.gender] = record
	context['records_by_age_group'] = data
	return render(request, 'age_group_records/records_for_distance.html', context)

def records_for_marathon(request, gender_code):
	gender = results_util.GENDER_CODES_INV.get(gender_code)
	if not gender:
		raise Http404()
	country = models.Country.objects.get(pk='RU')
	distance = models.Distance.objects.get(pk=results_util.DIST_MARATHON_ID)
	is_indoor = False

	context = user_edit_vars(request.user)
	distance_name = u'марафоне'
	context['page_title'] = u'Рекорды России на марафоне в возрастных группах. {}'.format(
		u'Мужчины' if gender == models.GENDER_MALE else u'Женщины')

	data = OrderedDict()
	records = country.record_result_set.filter(distance=distance, is_indoor=is_indoor, gender=gender, cur_place=1).exclude(
		age_group__age_group_type=models.RECORD_AGE_GROUP_TYPE_YOUNG).select_related(
		'result__race__event__series__city__region__country', 'result__race__event__city__region__country',
		'result__runner__user__user_profile', 'result__runner__city__region__country').order_by('age_group__age_min')
	for record in records:
		data[record.age_group] = record
	context['records_by_age_group'] = data
	context['gender'] = gender
	context['today'] = models.date2str(datetime.date.today())
	return render(request, 'age_group_records/records_for_marathon.html', context)
