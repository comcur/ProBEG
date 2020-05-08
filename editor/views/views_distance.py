# -*- coding: utf-8 -*-
from __future__ import division
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import permission_required
from django.db.models.expressions import RawSQL
from django.db.models.functions import Concat
from django.db.models.query import Prefetch
from django.db.models import F, Value
from django.http import HttpResponse
from collections import OrderedDict
from django.contrib import messages
from django.db.models import Count
from operator import itemgetter

from results import models
from editor import forms
from results.views.views_common import user_edit_vars
from .views_user_actions import log_form_change
from .views_common import group_required, update_distance, changes_history
from .views_document import docs_differences, docs_without_old_fields

# E.g. (4.300, км) -> (1, 4300), (2.5, ч) -> (2, 150)
def pair2type_length(value, unit):
	if unit == u"км":
		return models.TYPE_METERS, int(round(value * 1000))
	if unit in [u'м', u'метров']:
		return models.TYPE_METERS, int(round(value))
	if unit in [u'мили', u'миля', u'миль']:
		return models.TYPE_METERS, int(round(value * models.MILE_IN_METERS))
	if unit == u"суток":
		return models.TYPE_MINUTES, int(round(value * 24 * 60))
	if unit in [u'час', u'часа', u'часов', u'ч']:
		return models.TYPE_MINUTES, int(round(value * 60))
	if unit in [u'минут', u'мин']:
		return models.TYPE_MINUTES, int(round(value))
	if unit in [u"ступенек", u"ступеньки"]:
		return models.TYPE_STEPS, int(round(value))
	if unit == u"этажей":
		return models.TYPE_FLOORS, int(round(value))
	return models.TYPE_TRASH, int(round(value))

def cut_prefix(s, prefix):
	prefix_len = len(prefix)
	if s[:prefix_len] == prefix:
		s = s[prefix_len:]
	return s
def cut_suffix(s, suffix):
	suffix_len = len(suffix)
	if s[-suffix_len:] == suffix:
		s = s[:-suffix_len]
	return s

prefixes_to_cut = [u"(Шоссе) ", u"(Кросс-кантри) "]
suffixes_to_cut = [u" (женщины)", u" (мужчины)", u" (дети)", u" (до 12 лет)", u" (до 8 лет)", u" (гандикап)",
			u" (несоревновательная)", u" (несоревновательный)", u" (критериум)", u" (д)", u" (ю)"]

# Returns 2 params, distance and to_break.
# distance - stripped distance without suffixes and prefixes.
# if to_break, we just pass this distance and do not work with it
def process_distance(distance):
	res = distance.strip()
	to_break = False
	for suffix in suffixes_to_cut:
		res = cut_suffix(res, suffix)
	for prefix in prefixes_to_cut:
		res = cut_prefix(res, prefix)
	if "+" in res:
		to_break = True
	if "x" in res:
		to_break = True
	if res == "":
		to_break = True
	if res == u"1 верста (1076 м)":
		res = u"1076 м"
	elif res == u"1/3 версты (359 м)":
		res = u"359 м"
	elif res == u"1/2 версты (538 м)":
		res = u"538 м"
	elif res == u"2/3 версты (717 м)":
		res = u"717 м"
	elif res == u"10 верст (10.670 км)":
		res = u"10670 м"
	elif res == u"12.2 версты (13 км)":
		res = u"13000 м"
	elif res == u"5 верст (5.330 км)":
		res = u"5330 м"
	elif res == u"40 верст (42.672 км)":
		res = u"42672 м"
	elif res == u"2 версты (1.870 км)":
		res = u"1870 м"
	elif res == u"2 версты (2152 м)":
		res = u"2152 м"
	elif res == u"5 верст (5.335 км)":
		res = u"5335 м"
	elif res == u"10 верст (10.668 км)":
		res = u"10668 м"
	elif res == u"20 верст (21.336 км)":
		res = u"21336 м"
	elif res == u"5 верст (5.334 км)":
		res = u"5334 м"
	return res, to_break

# Print all distances from ProbegYear.Dists with some conditions
@group_required('admins')
def dist_splits(request):
	context = {}
	dists = {}
	endings = {}

	for event in models.Event.objects.exclude(distances_raw__startswith=u"вверх"):
		for distance in event.distances_raw.split(","):
			res, to_break = process_distance(dist)
			if to_break:
				continue
			dists[res] = dists.get(res, 0) + 1
			res_split = res.split()
			if len(res_split) == 2 and models.float_safe(res_split[0]) > 0:
				endings[res_split[1]] = endings.get(res_split[1], 0) + 1


	context['mylist'] = OrderedDict(sorted(dists.items(), key=lambda x: -x[1]))
	context['endings'] = OrderedDict(sorted(endings.items(), key=lambda x: -x[1]))
	context['prefixes_to_cut'] = ", ".join(prefixes_to_cut)
	context['suffixes_to_cut'] = ", ".join(suffixes_to_cut)

	return render(request, "editor/dist_splits.html", context)

# models.Distances to create
@group_required('admins')
def create_distances_from_dists(request):
	events = []
	races_added = 0

	for event in models.Event.objects.exclude(distances_raw__startswith=u"вверх").filter(cancelled=False).select_related(
			"series").prefetch_related("race_set").order_by("start_date", "series__id"):
		if event.race_set.count() > 0:
			continue
		dists_in_ProbegYear = set() # There will be all distances from ProbegYear.dists
		for distance in event.distances_raw.split(","):
			res, to_break = process_distance(distance)
			if to_break:
				continue
			res_split = res.split()
			if len(res_split) != 2 or models.float_safe(res_split[0]) == 0:
				continue
			dist_type, length = pair2type_length(models.float_safe(res_split[0]), res_split[1])

			distance = models.Distance.objects.filter(distance_type=dist_type, length=length)
			if distance.count() > 0:
				distance = distance[0]
			else:
				messages.warning(request, u"Не найдена дистанция типа {} длины {} у ProbegYear.id={}".format(
					dist_type, length, event.id))
				continue
			dists_in_ProbegYear.add(distance)
			race=models.Race(
				series_raw=event.series.id,
				event=event,
				distance=distance,
				distance_raw=distance.distance_raw,
				race_type_raw=distance.race_type_raw
				)
			race.save()
			races_added += 1
		if dists_in_ProbegYear:
			events.append((event.series.id, event.id, event.name, event.start_date, event.distances_raw,
				", ".join([x.name for x in sorted(dists_in_ProbegYear, key=lambda x: -x.length)])))

	context = {}
	context['mylist'] = events
	context['races_added'] = races_added

	return render(request, "editor/distances_just_added.html", context)

# Which distances are in ProbegYear but not in dist?
def new_distances():
	context = {}
	dists = set()
	new_dists = set()
	dists_in_base = models.Distance.objects

	# At first we collect all distances from ProbegYear.Dists
	for event in models.Event.objects.exclude(distances_raw__startswith=u"вверх"):
		for distance in event.distances_raw.split(","):
			res, to_break = process_distance(distance)
			if to_break:
				continue
			res_split = res.split()
			if len(res_split) != 2 or models.float_safe(res_split[0]) == 0:
				continue
			dist_type, length = pair2type_length(models.float_safe(res_split[0]), res_split[1])
			dists.add((dist_type, length, res))

	# And all distances from rezult.DISTANCE
	# for result in models_ak.Ak_result_v2.objects.values('distance').distinct():
	# 	distance = result['distance'].replace(",", ".")
	# 	if distance == u"20 км(2 кр":
	# 		distance = u"20 км"
	# 	if distance == u"20 км-сокр":
	# 		distance = u"20 км"
	# 	if distance == u"21. 0975 к":
	# 		distance = u"21.0975 км"
	# 	if distance == u"21. 1 км":
	# 		distance = u"21.1 км"
	# 	if distance == u"42.195":
	# 		distance = u"42.195 км"
	# 	res, to_break = process_distance(distance)
	# 	res_split = res.split()
	# 	if len(res_split) != 2 or models.float_safe(res_split[0]) == 0:
	# 		continue
	# 	dist_type, length = pair2type_length(models.float_safe(res_split[0]), res_split[1])
	# 	dists.add((dist_type, length, res))

	# And now check which of them are new
	for dist_type, length, name_raw in dists:
		if not dists_in_base.filter(distance_type=dist_type, length=length).exists():
			new_dists.add((dist_type, length, name_raw))
	return new_dists

# models.Distances to create
def dist_splits_differences(request):
	context = {}
	events = []

	for event in models.Event.objects.exclude(distances_raw__startswith=u"вверх").filter(cancelled=False).select_related(
			"series").prefetch_related("race_set").order_by("start_date", "series__id"):
		if event.race_set.count() > 0:
			continue
		dists_in_ProbegYear = set() # There will be all distances from ProbegYear.dists
		for distance in event.distances_raw.split(","):
			res, to_break = process_distance(distance)
			if to_break:
				continue
			res_split = res.split()
			if len(res_split) != 2 or models.float_safe(res_split[0]) == 0:
				continue
			dist_type, length = pair2type_length(models.float_safe(res_split[0]), res_split[1])

			distance = models.Distance.objects.filter(distance_type=dist_type, length=length)
			if distance.count() > 0:
				distance = distance[0]
			else:
				messages.warning(request, u"Не найдена дистанция типа {} длины {} у ProbegYear.id={}".format(
					dist_type, length, event.id))
				continue
			dists_in_ProbegYear.add(distance)
		if dists_in_ProbegYear:
			events.append((event.series.id, event.id, event.name, event.start_date, event.distances_raw,
				", ".join([x.name for x in sorted(dists_in_ProbegYear, key=lambda x: -x.length)])))
	return events

# Print all distances from database
@group_required('admins', 'editors')
def distances(request):
	context = user_edit_vars(request.user)
	context['mylist'] = models.Distance.objects.annotate(
		num_races=Count('race', distinct=True)).order_by('distance_type', 'length')

	return render(request, "editor/distances.html", context)

@group_required('admins', 'editors')
def distance_details(request, distance_id=None, distance=None,
		frmDistance=None, frmForDistance=forms.ForDistanceForm(auto_id='frmForDistance_%s'), create_new=False):
	if distance_id and not distance: # False if we are creating new distance
		distance = get_object_or_404(models.Distance, pk=distance_id)

	if distance and not frmDistance:
		frmDistance = forms.DistanceForm(instance=distance)

	context = user_edit_vars(request.user)
	context['distance'] = distance
	context['frmDistance'] = frmDistance
	context['frmForDistance'] = frmForDistance
	context['create_new'] = create_new
	context['form_title'] = u'Создание новой дистанции' if create_new else u'Дистанция {} (id {})'.format(distance, distance.id)

	if not create_new:
		counts = OrderedDict()
		counts[models.Race._meta.db_table] = distance.race_set.count()
		counts[u'Фактические дистанции'] = distance.distance_real_set.count()
		counts[models.Split._meta.db_table] = distance.split_set.count()
		context['counts'] = counts

	return render(request, "editor/distance_details.html", context)

@group_required('admins')
def distance_changes_history(request, distance_id):
	distance = get_object_or_404(models.Distance, pk=distance_id)
	context = user_edit_vars(request.user)
	return changes_history(request, context, distance, distance.get_editor_url())

@group_required('admins')
def distance_update(request, distance_id):
	distance = get_object_or_404(models.Distance, pk=distance_id)
	ok_to_save = True
	if (request.method == 'POST') and request.POST.get('frmDistance_submit', False):
		form = forms.DistanceForm(request.POST, instance=distance)
		if form.is_valid():
			form.save()
			log_form_change(request.user, form, action=models.ACTION_UPDATE)
			messages.success(request, u'Дистанция «{}» успешно обновлена. Проверьте, всё ли правильно.'.format(distance))
			update_distance(request, distance)
			return redirect(distance.get_editor_url())
		else:
			messages.warning(request, u"Дистанция не обновлена. Пожалуйста, исправьте ошибки в форме.")
	else:
		form = forms.DistanceForm(instance=distance)
	return distance_details(request, distance_id=distance_id, distance=distance, frmDistance=form)

@group_required('admins', 'editors')
def distance_create(request):
	distance = models.Distance()
	if (request.method == 'POST') and request.POST.get('frmDistance_submit', False):
		form = forms.DistanceForm(request.POST, instance=distance)
		if form.is_valid():
			form.instance.created_by = request.user
			distance = form.save()
			log_form_change(request.user, form, action=models.ACTION_CREATE)
			if (distance.name == '') and distance.distance_type:
				distance.name = distance.nameFromType()
				distance.save()
			messages.success(request, u'Дистанция «{}» успешно создана. Проверьте, всё ли правильно.'.format(distance))
			return redirect(distance.get_editor_url())
		else:
			messages.warning(request, u"Дистанция не создана. Пожалуйста, исправьте ошибки в форме.")
	else:
		form = forms.DistanceForm(instance=distance)
	return distance_details(request, distance=distance, frmDistance=form, create_new=True)

@group_required('admins')
def distance_delete(request, distance_id):
	distance = get_object_or_404(models.Distance, pk=distance_id)
	has_dependent_objects = distance.has_dependent_objects()
	ok_to_delete = False
	if (request.method == 'POST') and request.POST.get('frmForDistance_submit', False):
		form = forms.ForDistanceForm(request.POST, auto_id='frmForDistance_%s')
		if form.is_valid():
			if has_dependent_objects:
				new_distance = form.cleaned_data['new_distance']
				if new_distance != distance:
						ok_to_delete = True
				else:
					messages.warning(request, u'Нельзя заменить дистанцию на неё же.')
			else: # There are no dependent races or splits, so we can delete it
				ok_to_delete = True
		else:
			messages.warning(request, u"Дистанция не создана. Пожалуйста, исправьте ошибки в форме.")
	else:
		form = forms.ForDistanceForm(auto_id='frmForDistance_%s')
		messages.warning(request, u"Вы не указали город для удаления.")

	if ok_to_delete:
		if has_dependent_objects:
			update_distance(request, distance, new_distance)
		models.log_obj_delete(request.user, distance)
		distance.delete()
		messages.success(request, u'Дистанция «{}» успешно удалена.'.format(distance))
		if has_dependent_objects:
			return redirect(new_distance.get_editor_url())
		else:
			return redirect('editor:distances')

	return distance_details(request, distance_id=distance_id, distance=distance, frmForDistance=form)
