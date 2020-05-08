# -*- coding: utf-8 -*-
from __future__ import division
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import permission_required
from django.db.models.query import Prefetch
from django.contrib import messages
import datetime

from results import models
from results.forms import UserNameForm
from editor import forms
from results.views.views_common import user_edit_vars
from .views_common import group_required, update_runner, changes_history
from .views_user_actions import log_form_change
from .views_stat import update_runner_stat

@group_required('admins')
def runner_details(request, runner_id=None, runner=None, frmRunner=None, frmName=None):
	if runner is None: # False if we are creating new runner
		runner = get_object_or_404(models.Runner, pk=runner_id)
	if frmRunner is None:
		initial = {}
		if runner.city:
			initial['city'] = runner.city
			initial['region'] = runner.city.region.id
		frmRunner = forms.RunnerForm(instance=runner, initial=initial)
	if frmName is None:
		frmName = UserNameForm()
	context = {}
	context['runner'] = runner
	context['form'] = frmRunner
	context['frmName'] = frmName

	if runner.id:
		context['page_title'] = u'{} (id {})'.format(runner.name(), runner.id)
		context['names'] = runner.extra_name_set.order_by('lname', 'fname', 'midname')
	else:
		context['page_title'] = u'Создание нового бегуна'
	return render(request, "editor/runner_details.html", context)

@group_required('admins')
def runner_update(request, runner_id):
	runner = get_object_or_404(models.Runner, pk=runner_id)
	if 'frmRunner_submit' in request.POST:
		frmRunner = forms.RunnerForm(request.POST, instance=runner)
		if frmRunner.is_valid():
			runner = frmRunner.save()
			log_form_change(request.user, frmRunner, action=models.ACTION_UPDATE, exclude=['country', 'region'])
			messages.success(request, u'Бегун «{}» успешно обновлён. Изменены поля: {}'.format(
				runner.name(), ", ".join(frmRunner.changed_data)))
			klb_person = runner.klb_person
			if klb_person:
				fields_for_klb_person = []
				if ('birthday' in frmRunner.changed_data) and runner.birthday_known:
					fields_for_klb_person.append('birthday')
				for field in ['lname', 'fname', 'midname', 'gender', 'city_id']:
					if field in frmRunner.changed_data:
						fields_for_klb_person.append(field)
				if fields_for_klb_person:
					for field in fields_for_klb_person:
						setattr(klb_person, field, getattr(runner, field))
					klb_person.clean()
					klb_person.save()
					if ('birthday' in fields_for_klb_person) or ('gender' in fields_for_klb_person):
						participant = klb_person.klb_participant_set.filter(match_year=models.CUR_KLB_YEAR).first()
						if participant:
							participant.fill_age_group()
					models.log_obj_create(request.user, klb_person, models.ACTION_UPDATE, field_list=fields_for_klb_person, comment=u'При правке бегуна')
					messages.success(request, u'У участника КЛБМатчей изменены поля: {}'.format(", ".join(fields_for_klb_person)))
			return redirect(runner)
		else:
			messages.warning(request, u"Бегун не обновлён. Пожалуйста, исправьте ошибки в форме.")
	else:
		frmRunner = None
	return runner_details(request, runner_id=runner_id, runner=runner, frmRunner=frmRunner)

# Needs to be called only if runner.has_dependent_objects() == True
def delete_runner_for_another(request, creator, runner, has_dependent_objects, new_runner):
	if has_dependent_objects:
		update_runner(request, creator, runner, new_runner)
		update_runner_stat(runner=new_runner)
		if new_runner.user:
			update_runner_stat(user=new_runner.user)
	models.log_obj_delete(creator, runner)
	if request:
		messages.success(request, u'Бегун {} (id {}) успешно удалён.'.format(runner.name(), runner.id))
	runner.delete()

@group_required('admins')
def runner_delete(request, runner_id):
	runner = get_object_or_404(models.Runner, pk=runner_id)
	has_dependent_objects = runner.has_dependent_objects()
	ok_to_delete = False
	form = None
	new_runner = None
	if 'frmForRunner_submit' in request.POST:
		if has_dependent_objects:
			new_runner_id = models.int_safe(request.POST.get('select_runner'))
			if new_runner_id:
				if new_runner_id != runner.id:
					new_runner = models.Runner.objects.filter(pk=new_runner_id).first()
					if new_runner:
						is_merged, msgError = new_runner.merge(runner, request.user)
						if is_merged:
							ok_to_delete = True
						else:
							messages.warning(request, u'Не удалось объединить бегунов. Ошибка: {}'.format(msgError))
					else:
						messages.warning(request, u'Бегун, на которого нужно заменить текущего, не найден.')
				else:
					messages.warning(request, u'Нельзя заменить бегуна на него же.')
			else:
				messages.warning(request, u'Бегун, на которого нужно заменить текущего, не указан.')
		else: # There are no results for runner, so we just delete him
			ok_to_delete = True
	else:
		messages.warning(request, u"Вы не указали бегуна для удаления.")

	if ok_to_delete:
		delete_runner_for_another(request, request.user, runner, has_dependent_objects, new_runner)
		return redirect(new_runner if has_dependent_objects else 'results:runners') 

	return runner_details(request, runner_id=runner_id, runner=runner)

@group_required('admins', 'editors')
def runner_create(request, lname='', fname=''):
	runner = models.Runner(created_by=request.user, lname=lname, fname=fname)
	if 'frmRunner_submit' in request.POST:
		form = forms.RunnerForm(request.POST, instance=runner)
		if form.is_valid():
			form.save()
			log_form_change(request.user, form, action=models.ACTION_CREATE)
			messages.success(request, u'Бегун «{}» успешно создан. Проверьте, всё ли правильно.'.format(runner))
			return redirect(runner.get_editor_url())
		else:
			messages.warning(request, u"Бегун не создан. Пожалуйста, исправьте ошибки в форме.")
	else:
		form = None
	return runner_details(request, runner=runner, frmRunner=form)

@group_required('admins')
def runner_changes_history(request, runner_id):
	runner = get_object_or_404(models.Runner, pk=runner_id)
	context = user_edit_vars(request.user)
	return changes_history(request, context, runner, runner.get_absolute_url())

@group_required('admins')
def runner_update_stat(request, runner_id):
	runner = get_object_or_404(models.Runner, pk=runner_id)
	update_runner_stat(runner=runner)
	messages.success(request, u'Статистика успешно обновлена')
	return redirect('results:runner_details', runner_id=runner.id)

@group_required('admins')
def runner_name_add(request, runner_id):
	runner = get_object_or_404(models.Runner, pk=runner_id)
	extra_name = models.Extra_name(runner=runner, added_by=request.user)
	frmName = None
	if 'frmName_submit' in request.POST:
		frmName = UserNameForm(request.POST, instance=extra_name)
		if frmName.is_valid():
			frmName.save()
			log_form_change(request.user, frmName, action=models.ACTION_CREATE)
			messages.success(request, u'Новое имя успешно добавлено')
			return redirect(runner)
		else:
			messages.warning(request, u'Данные для нового имени указаны с ошибкой. Пожалуйста, исправьте ошибки в форме.')
	return runner_details(request, runner_id=runner_id, runner=runner, frmName=frmName)

@group_required('admins')
def runner_name_delete(request, runner_id, name_id):
	runner = get_object_or_404(models.Runner, pk=runner_id)
	name = models.Extra_name.objects.filter(pk=name_id, runner=runner).first()
	if name:
		models.log_obj_create(request.user, name, models.ACTION_DELETE, comment=u'Удалено со страницы бегуна')
		name.delete()
		messages.success(request, u'Имя успешно удалено.')
	else:
		messages.warning(request, u'Имя для удаления не найдено. Ничего не удалено.')
	return redirect(runner)

def merge_runners_with_same_name_and_birthday():
	pass