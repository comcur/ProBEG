# -*- coding: utf-8 -*-
from __future__ import division
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.forms import modelformset_factory
from django.contrib import messages
from django.db.models import Count
import datetime

from results import models
from editor import forms
from .views_user_actions import log_document_formset
from .views_common import group_required
from .views_stat import update_race_runners_stat, update_runner_stat
from .views_result import update_result_connections, fill_race_headers

def getResultFormSet(race, data=None):
	ResultFormSet = modelformset_factory(models.Result, form=forms.SmallResultForm, can_delete=True, extra=0)
	res = ResultFormSet(
		data=data,
		queryset=models.Result.objects.filter(race=race).order_by('status', 'place', 'lname', 'fname', 'midname', 'id').select_related('category_size')
	)
	for form in res.forms:
		form.fields['DELETE'].widget.attrs.update({'class': 'chkbox'})
	return res

@group_required('admins')
def race_details(request, race_id=None, race=None, frmResults=None):
	if not race:
		race = get_object_or_404(models.Race, pk=race_id)
	context = {}

	if not frmResults:
		frmResults = getResultFormSet(race)
	context['frmResults'] = frmResults

	context['race'] = race
	context['event'] = race.event
	context['page_title'] = u'{}: редактирование результатов'.format(race)

	return render(request, "editor/race_details.html", context)

@group_required('admins')
def race_update(request, race_id):
	race = get_object_or_404(models.Race, pk=race_id)
	context = {}

	if 'frmResults_submit' in request.POST:
		formset = getResultFormSet(race, data=request.POST)
		if formset.is_valid():
			formset.save()
			log_document_formset(request.user, race.event, formset)
			for result, changed_data in formset.changed_objects:
				update_result_connections(request.user, result, changed_data)
			messages.success(request, (u'Результаты забега «{}» успешно обновлены: {} результатов добавлено, {} обновлено, '
				+ u'{} удалено. Проверьте, всё ли правильно.').format(
				race, len(formset.new_objects), len(formset.changed_objects), len(formset.deleted_objects)))
			race.was_checked_for_klb = False
			race.save()
			if race.loaded == models.RESULTS_LOADED:
				fill_race_headers(race)
			return redirect(race.get_results_editor_url())
		else:
			messages.warning(request, u"Результаты забега «{}» не обновлены. Пожалуйста, исправьте ошибки в форме.".format(race))
	else:
		formset = None
	return race_details(request, race_id=race_id, race=race, frmResults=formset)

@group_required('admins')
def race_update_stat(request, race_id):
	race = get_object_or_404(models.Race, pk=race_id)
	n_runners = update_race_runners_stat(race)
	messages.success(request, u'Обновлена статистика у участников забега: {} человек'.format(n_runners))
	return redirect(race)

@login_required
def race_add_unoff_result(request, race_id):
	race = get_object_or_404(models.Race, pk=race_id)
	event = race.event
	user = request.user
	if 'frmAddResult_submit' in request.POST:
		runner = models.Runner.objects.filter(pk=request.POST.get('select_runner')).first()
		if runner:
			has_rights_for_this_runner = models.is_admin(user) or (runner.id in models.get_runner_ids_for_user(user))

			if has_rights_for_this_runner:
				result_in_this_race = runner.result_set.filter(race=race).first()
				if result_in_this_race is None:
					result_str = request.POST.get('result_str', '')
					result = race.parse_result(result_str)
					if result > 0:
						result = models.Result(
							runner=runner,
							user=runner.user,
							race=race,
							time_raw=result_str,
							result=result,
							status=models.STATUS_FINISHED,
							source=models.RESULT_SOURCE_USER,
							loaded_by=user,
						)
						result.save()
						models.log_obj_create(user, event, models.ACTION_UNOFF_RESULT_CREATE, child_object=result)
						update_runner_stat(runner=runner)
						messages.success(request, u'Результат {} бегуну {} успешно добавлен'.format(result, runner.name()))
					else:
						if race.distance.distance_type == models.TYPE_MINUTES:
							messages.warning(request, u'Пожалуйста, введите в качестве результата число метров')
						else:
							messages.warning(request, u'Пожалуйста, введите результат в формате ЧЧ:ММ:СС или ЧЧ:ММ:СС,хх')
				else:
					messages.warning(request, u'У этого бегуна уже есть результат {} на этой дистанции'.format(result_in_this_race))
			else:
				messages.warning(request, u'У Вас нет прав добавлять результат бегуну {} {} (id {})'.format(runner.fname, runner.lname, runner.id))
		else:
			messages.warning(request, u'Выбранный бегун не найден')
	return redirect(race)

@group_required('admins')
def race_delete_off_results(request, race_id):
	race = get_object_or_404(models.Race, pk=race_id)
	results = race.get_official_results()
	if results.exists():
		results.delete()
		fill_race_headers(race)
		race.loaded = models.RESULTS_NOT_LOADED
		race.loaded_from = ''
		race.was_checked_for_klb = False
		race.save()
		models.log_obj_create(request.user, race.event, models.ACTION_RACE_UPDATE, child_object=race, field_list=['loaded', 'loaded_from', 'was_checked_for_klb'],
			comment=u'При удалении всех официальных результатов')
		messages.success(request, u'Все официальные результаты на забеге {} успешно удалены'.format(race.name_with_event()))
	else:
		messages.warning(request, u'Официальных результатов на забеге {} не нашлось. Ничего не делаем'.format(race.name_with_event()))
	return redirect(race)
