# -*- coding: utf-8 -*-
from __future__ import division
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import permission_required
from django.core.files.temp import NamedTemporaryFile
from django.forms import modelformset_factory
from django.core.urlresolvers import reverse
from django.db.models.query import Prefetch
from django.db.models import Count, Q
from django.contrib import messages
from django.core.files import File
import datetime

from results import models
from editor import forms
from .views_user_actions import log_form_change, log_document_formset
from .views_common import group_required, check_rights, changes_history

def getRaceCheckFormSet(event, data=None):
	RaceCheckFormSet = modelformset_factory(models.Race, form=forms.RaceCheckForm, extra=0)
	return RaceCheckFormSet(
		data=data,
		queryset=event.race_set.order_by('distance__distance_type', '-distance__length', 'precise_name'),
	)

N_EXTRA_QUESTIONS = 1
N_EXTRA_COSTS = 3
def getRegQuestionFormSet(event, user, data=None, files=None):
	RegQuestionFormSet = modelformset_factory(models.Reg_question, form=forms.RegQuestionForm, can_delete=True, extra=N_EXTRA_QUESTIONS)
	return RegQuestionFormSet(
		data=data,
		files=files,
		queryset=event.reg_question_set.all(),
		initial=[{'event': event, 'created_by': user}] * N_EXTRA_QUESTIONS
	)

def getRegRaceFormSet(event, data=None):
	RegRaceFormSet = modelformset_factory(models.Reg_race_details, form=forms.RegRaceForm, can_delete=True, extra=0)
	return RegRaceFormSet(
		data=data,
		queryset=models.Reg_race_details.objects.filter(race__event=event).order_by('race__distance__distance_type', '-race__distance__length', 'race__precise_name'),
	)

def getRaceCostFormSet(race, user, data=None):
	RaceCostFormSet = modelformset_factory(models.Race_cost, form=forms.RaceCostForm, formset=forms.RaceCostFormSet, can_delete=True, extra=N_EXTRA_COSTS)
	return RaceCostFormSet(
		data=data,
		queryset=race.race_cost_set.all(),
		initial=[{'race': race, 'created_by': user}] * N_EXTRA_COSTS
	)

def getRegChoiceFormSet(question, user, data=None):
	RegChoiceFormSet = modelformset_factory(models.Reg_question_choice, form=forms.RegChoiceForm, formset=forms.RegChoiceFormSet, can_delete=True, extra=N_EXTRA_QUESTIONS)
	return RegChoiceFormSet(
		data=data,
		queryset=question.reg_question_choice_set.order_by('number'),
		initial=[{'reg_question': question, 'created_by': user}] * N_EXTRA_QUESTIONS
	)

def try_move_choice(choice_set, choice, move): # For choices and questions
	choice_set = choice_set.order_by('number')
	was_moved = False
	max_choice = choice_set.last()
	if max_choice is None:
		return False
	max_number = max_choice.number
	if (move == forms.MOVE_TO_FIRST) and choice.number > 1:
		for ch in choice_set.filter(number__range=(1, choice.number - 1)):
			ch.number += 1
			ch.save()
		choice.number = 1
		choice.save()
		return True
	elif (move == forms.MOVE_TO_PREV) and choice.number > 1:
		ch = choice_set.filter(number__lt=choice.number).last()
		if ch:
			ch.number = choice.number
			ch.save()
			choice.number -= 1
			choice.save()
			return True
	elif (move == forms.MOVE_TO_NEXT) and choice.number < max_number:
		ch = choice_set.filter(number__gt=choice.number).first()
		if ch:
			ch.number = choice.number
			ch.save()
			choice.number += 1
			choice.save()
			return True
	elif (move == forms.MOVE_TO_LAST) and choice.number < max_number:
		for ch in choice_set.filter(number__range=(choice.number + 1, max_number)):
			ch.number -= 1
			ch.save()
		choice.number = max_number
		choice.save()
		return True
	return False

def refresh_numbers(choice_set): # For choices and questions
	counter = 1
	for choice in choice_set.order_by('number'):
		if choice.number != counter:
			choice.number = counter
			choice.save()
		counter += 1

@group_required('editors', 'admins')
def registration_details(request, event_id=None):
	registration = get_object_or_404(models.Registration, event_id=event_id)
	event = registration.event
	context, has_rights, target = check_rights(request, event=event)
	if not has_rights:
		return target

	user = request.user
	frmRegistration = None
	frmQuestions = None
	frmNewRace = None
	frmRaces = None

	if 'frmRegistration_submit' in request.POST:
		frmRegistration = forms.RegistrationForm(request.POST, instance=registration)
		if frmRegistration.is_valid():
			if ('is_open' in frmRegistration.changed_data) and frmRegistration.instance.is_open:
				if not models.Reg_race_details.objects.filter(race__event=event, is_open=True).exists():
					frmRegistration.instance.is_open = False
					messages.warning(request, u'Регистрация оставлена закрытой, поскольку закрыты регистрации на все дистанции. Сначала откройте хотя бы одну ниже')
			registration = frmRegistration.save()
			log_form_change(user, frmRegistration, action=models.ACTION_UPDATE)
			messages.success(request, u'Регистрация на забег «{}» успешно обновлена. Проверьте, всё ли правильно.'.format(event))
			return redirect(registration.get_editor_url())
		else:
			messages.warning(request, u"Регистрация не обновлена. Пожалуйста, исправьте ошибки в форме.")
	elif 'frmQuestions_submit' in request.POST:
		frmQuestions = getRegQuestionFormSet(event, user, data=request.POST, files=request.FILES)
		if frmQuestions.is_valid():
			instances = frmQuestions.save()
			log_document_formset(user, registration, frmQuestions)

			if len(frmQuestions.deleted_objects):
				refresh_numbers(event.reg_question_set)

			for question in frmQuestions.new_objects:
				for race in event.get_reg_race_set():
					models.Reg_question_race.objects.create(
						reg_question=question,
						race=race,
						added_by=user,
					)

			messages.success(request, (u'Вопросы регистрации на забег«{}» успешно обновлены: {} вопросов добавлено, {} обновлено, '
				+ u'{} удалено. Проверьте, всё ли правильно.').format(
				event, len(frmQuestions.new_objects), len(frmQuestions.changed_objects), len(frmQuestions.deleted_objects)))
			return redirect(registration.get_editor_url())
		else:
			messages.warning(request, u"Вопросы регистрации не обновлены. Пожалуйста, исправьте ошибки в форме.")
	elif 'frmRaces_submit' in request.POST:
		frmRaces = getRegRaceFormSet(event, data=request.POST)
		if frmRaces.is_valid():
			instances = frmRaces.save()
			log_document_formset(user, registration, frmRaces)
			messages.success(request, (u'Дистанции регистрации на забег«{}» успешно обновлены: {} вопросов добавлено, {} обновлено, '
				+ u'{} удалено. Проверьте, всё ли правильно.').format(
				event, len(frmRaces.new_objects), len(frmRaces.changed_objects), len(frmRaces.deleted_objects)))
			return redirect(registration.get_editor_url())
		else:
			messages.warning(request, u"Дистанции не обновлены. Пожалуйста, исправьте ошибки в форме.")
	elif 'frmNewRace_submit' in request.POST:
		frmNewRace = forms.RegNewRaceForm(event=event, data=request.POST)
		if frmNewRace.is_valid():
			race_new = frmNewRace.cleaned_data['race_new']
			race_template = frmNewRace.cleaned_data.get('race_template')
			if race_template:
				reg_race_details = race_template.reg_race_details
				reg_race_details.id = None
			else:
				reg_race_details = models.Reg_race_details()
			reg_race_details.race = race_new
			reg_race_details.created_by = user
			reg_race_details.save()
			models.log_obj_create(user, registration, models.ACTION_REG_RACE_CREATE, child_object=reg_race_details, comment=u'При добавлении регистрации на дистанцию')
			if race_template:
				for question in race_template.reg_question_set.all():
					models.Reg_question_race.objects.create(
						reg_question=question,
						race=race_new,
						added_by=user,
					)
				for race_cost in list(race_template.race_cost_set.all()):
					race_cost_new = race_cost
					race_cost_new.id = None
					race_cost_new.race = race_new
					race_cost_new.created_by = user
					race_cost_new.save()
					models.log_obj_create(user, registration, models.ACTION_RACE_COST_CREATE, child_object=race_cost_new, comment=u'При добавлении регистрации на дистанцию')
				messages.success(request, u'Регистрация на дистанцию {} по образцу дистанции {} открыта. Проверьте, всё ли правильно'.format(
					race_new, race_template))
			else:
				race_cost_new = models.Race_cost.objects.filter(race__event=event, finish_date=None).first()
				if race_cost_new:
					race_cost_new.id = None
				else:
					race_cost_new = models.Race_cost(cost=models.Race_cost.get_default_cost())
				race_cost_new.race = race_new
				race_cost_new.created_by = user
				race_cost_new.save()
				models.log_obj_create(user, registration, models.ACTION_RACE_COST_CREATE, child_object=race_cost_new, comment=u'При добавлении регистрации на дистанцию')
				messages.success(request, u'Регистрация на дистанцию {} открыта. Проверьте, всё ли правильно, и добавьте нужные цены регистрации и вопросы'.format(
					race_new))
			return redirect(registration.get_editor_url())
		else:
			messages.warning(request, u"Новая регистрация не создана. Пожалуйста, исправьте ошибки в форме.")
	elif 'frmDeleteRegistration_submit' in request.POST:
		if not registration.has_dependent_objects():
			models.log_obj_delete(user, registration)
			registration.delete()
			messages.success(request, u'Регистрация успешно удалена.')
			return redirect(event)
		else:
			messages.warning(request, u'Для удаления регистрации не должно быть ни вопросов в ней, ни уже зарегистрированных людей')
	else:
		for question in event.reg_question_set.all():
			if 'move_question_{}_submit'.format(question.id) in request.POST:
				if try_move_choice(event.reg_question_set, question, models.int_safe(request.POST.get('move_question_{}'.format(question.id)))):
					messages.success(request, u'Вопрос «{}» успешно перемещён'.format(question.title))
				else:
					messages.success(request, u'Вопрос «{}» оставлен на месте'.format(question.title))
				return redirect(registration.get_editor_url())

	context['event'] = event
	context['registration'] = registration
	context['n_questions'] = event.reg_question_set.count()
	context['move_choices'] = forms.QUESTION_MOVE_CHOICES
	context['races_with_registration'] = event.get_reg_race_set()
	context['page_title'] = u'Регистрация на забег «{}»'.format(event)

	context['frmRegistration'] = frmRegistration if frmRegistration else forms.RegistrationForm(instance=registration)
	context['frmQuestions'] = frmQuestions if frmQuestions else getRegQuestionFormSet(event, user)
	context['frmRaces'] = frmRaces if frmRaces else getRegRaceFormSet(event)
	if context['races_with_registration'].count() < event.race_set.count():
		context['frmNewRace'] = frmNewRace if frmNewRace else forms.RegNewRaceForm(event=event)

	return render(request, "editor/registration/reg_details.html", context)

@group_required('editors', 'admins')
def registration_info(request, event_id=None):
	registration = get_object_or_404(models.Registration, event_id=event_id)
	event = registration.event
	context, has_rights, target = check_rights(request, event=event)
	if not has_rights:
		return target
	context['event'] = event
	context['registration'] = registration
	context['move_choices'] = forms.QUESTION_MOVE_CHOICES
	context['races_with_registration'] = event.get_reg_race_set()
	context['page_title'] = u'Регистрация на забег «{}»'.format(event)

	return render(request, "editor/registration/reg_info.html", context)

@group_required('editors', 'admins')
def question_details(request, question_id):
	question = get_object_or_404(models.Reg_question, pk=question_id)
	event = question.event
	context, has_rights, target = check_rights(request, event=event)
	if not has_rights:
		return target
	if not hasattr(event, 'registration'):
		messages.warning(request, u'Регистрация на этот забег ещё не создана')
		return redirect(event)

	registration = event.registration
	user = request.user
	frmChoices = None
	frmQuestion = None

	if 'frmQuestion_submit' in request.POST:
		frmChoices = getRegChoiceFormSet(question, user, data=request.POST)
		frmQuestion = forms.RegQuestionRaceForm(request.POST, files=request.FILES, instance=question)
		if frmChoices.is_valid() and frmQuestion.is_valid():
			if frmQuestion.has_changed():
				old_question_race_ids = set(question.race_set.values_list('pk', flat=True))
				question = frmQuestion.save(commit=False)
				for race in event.get_reg_race_set():
					if (race in frmQuestion.cleaned_data['race_set']) and (race.id not in old_question_race_ids):
						models.Reg_question_race.objects.create(reg_question=question, race=race, added_by=user)
						# messages.success(request, u'Вопрос добавлен на дистанцию {}'.format(race))
					elif (race not in frmQuestion.cleaned_data['race_set']) and (race.id in old_question_race_ids):
						models.Reg_question_race.objects.filter(reg_question=question, race=race).delete()
						# messages.success(request, u'Вопрос убран с дистанции {}'.format(race))
				question.save()
				log_form_change(user, frmQuestion, action=models.ACTION_QUESTION_UPDATE, obj=registration)
				messages.success(request, u'Параметры вопроса обновлены. Проверьте, всё ли правильно.')

			if frmChoices.has_changed():
				frmChoices.save()
				log_document_formset(user, registration, frmChoices)
				if len(frmChoices.deleted_objects):
					refresh_numbers(question.reg_question_choice_set)
				messages.success(request, (u'Варианты ответов на вопрос «{}» успешно обновлены: {} вариантов добавлено, {} обновлено, '
					+ u'{} удалено. Проверьте, всё ли правильно.').format(
					event, len(frmChoices.new_objects), len(frmChoices.changed_objects), len(frmChoices.deleted_objects)))
			return redirect(question.get_editor_url())
		else:
			messages.warning(request, u"Вопросы регистрации не обновлены. Пожалуйста, исправьте ошибки в форме.")
	else:
		for choice in question.reg_question_choice_set.all():
			if 'move_choice_{}_submit'.format(choice.id) in request.POST:
				if try_move_choice(question.reg_question_choice_set, choice, models.int_safe(request.POST.get('move_choice_{}'.format(choice.id)))):
					messages.success(request, u'Пункт «{}» успешно перемещён'.format(choice.name))
				else:
					messages.success(request, u'Пункт «{}» оставлен на месте'.format(choice.name))
				return redirect(question.get_editor_url())
		frmQuestion = forms.RegQuestionRaceForm(instance=question)
		frmChoices = getRegChoiceFormSet(question, user)

	context['event'] = event
	context['question'] = question
	context['frmChoices'] = frmChoices
	context['frmQuestion'] = frmQuestion
	context['move_choices'] = forms.QUESTION_MOVE_CHOICES

	context['page_title'] = u'Регистрация на забег «{}»'.format(event)
	return render(request, "editor/registration/reg_question_details.html", context)

@group_required('editors', 'admins')
def reg_race_details(request, race_id):
	race = get_object_or_404(models.Race, pk=race_id)
	event = race.event
	context, has_rights, target = check_rights(request, event=event)
	if not has_rights:
		return target
	if not hasattr(event, 'registration'):
		messages.warning(request, u'Регистрация на этот забег ещё не создана')
		return redirect(event)

	registration = event.registration
	user = request.user
	frmRace = None

	if 'frmRace_submit' in request.POST:
		frmRace = getRaceCostFormSet(race, user, data=request.POST)
		if frmRace.is_valid():
				frmRace.save()
				log_document_formset(user, registration, frmRace)
				messages.success(request, (u'Цены успешно обновлены: {} цен добавлено, {} обновлено, {} удалено. Проверьте, всё ли правильно.').format(
					len(frmRace.new_objects), len(frmRace.changed_objects), len(frmRace.deleted_objects)))
				return redirect(race.get_reg_editor_url())
		else:
			messages.warning(request, u"Цены не обновлены. Пожалуйста, исправьте ошибки в форме.")
	else:
		frmRace = getRaceCostFormSet(race, user)

	context['event'] = event
	context['race'] = race
	context['frmRace'] = frmRace

	context['page_title'] = u'Стоимость регистрации на дистанцию {} забега «{}»'.format(race, event)
	return render(request, "editor/registration/reg_race_details.html", context)

@group_required('editors', 'admins')
def registration_changes_history(request, event_id):
	registration = get_object_or_404(models.Registration, event_id=event_id)
	event = registration.event
	context, has_rights, target = check_rights(request, event=event)
	if not has_rights:
		return target
	return changes_history(request, context, registration, registration.get_editor_url())

@group_required('admins')
def registration_create_step1(request, event_id, cloned_event_id=None):
	event = get_object_or_404(models.Event, pk=event_id)
	if event.is_in_past():
		messages.warning(request, u'Этот забег уже прошёл. На него нельзя открыть регистрацию')
		return redirect(event)
	if hasattr(event, 'registration'):
		messages.warning(request, u'Регистрация на этот забег уже создана')
		return redirect(event.registration.get_details_url())
	user = request.user
	context = {}
	context['event'] = event

	registration = None
	if cloned_event_id: # Clone event from event with this id
		cloned_event = get_object_or_404(models.Event, pk=cloned_event_id)
		if hasattr(cloned_event, 'registration'):
			registration = cloned_event.registration
			registration.id = None
	if registration is None:
		registration = models.Registration()
		registration.start_date = datetime.datetime.combine(datetime.date.today() + datetime.timedelta(days=1), datetime.time.min)
		registration.finish_date = datetime.datetime.combine(event.start_date - datetime.timedelta(days=2), datetime.time.max)
	registration.created_by = request.user
	registration.event = event
	if 'frmRegistration_submit' in request.POST:
		frmRegistration = forms.RegistrationForm(request.POST, instance=registration)
		frmSampleRace = forms.RegRaceForm(request.POST, is_sample=True)
		formset = getRaceCheckFormSet(event, request.POST)
		if frmRegistration.is_valid() and frmSampleRace.is_valid() and formset.is_valid():
			registration = frmRegistration.save()
			log_form_change(user, frmRegistration, action=models.ACTION_CREATE)

			sample_race_details = frmSampleRace.instance

			for raceform in formset:
				if raceform.cleaned_data['is_checked']:
					reg_race_details = models.Reg_race_details(race=raceform.instance, created_by=user)
					for field in forms.RegRaceForm.Meta.fields:
						if hasattr(sample_race_details, field):
							if field != 'created_by':
								setattr(reg_race_details, field, getattr(sample_race_details, field))
					reg_race_details.save()
					models.log_obj_create(user, registration, models.ACTION_REG_RACE_CREATE, child_object=reg_race_details, comment=u'При создании регистрации')
			return redirect(registration.get_create_step2_url())
		else:
			messages.warning(request, u"Регистрация не создана. Пожалуйста, исправьте ошибки в форме.")
	else:
		frmRegistration = forms.RegistrationForm(instance=registration)
		frmSampleRace = forms.RegRaceForm(is_sample=True)
		formset = getRaceCheckFormSet(event)
	context['frmRegistration'] = frmRegistration
	context['frmSampleRace'] = frmSampleRace
	context['formset'] = formset
	return render(request, "editor/registration/reg_create_step1.html", context)

N_PRICE_COLS_DEFAULT = 4
COMMISSION_TYPE_PARTICIPANT = 1
COMMISSION_TYPE_ORGANISER = 2
COMMISSION_PERCENT = 0.059

TSHIRT_FREE = 1
TSHIRT_FOR_MONEY = 2
@group_required('admins')
def registration_create_step2(request, event_id):
	user = request.user
	event = get_object_or_404(models.Event, pk=event_id)
	if not hasattr(event, 'registration'):
		messages.warning(request, u'Регистрация на этот забег ещё не создана')
		return redirect(event)
	registration = event.registration
	if registration.is_step2_passed:
		messages.warning(request, u'Вы уже прошли этот шаг. Теперь вы можете править цены на регистрацию на вкладках отдельных дистанций')
		return redirect(registration.get_editor_url())
	if models.Race_cost.objects.filter(race__event=event).exists():
		registration.is_step2_passed = True
		registration.save()
		models.log_obj_create(user, registration, models.ACTION_UPDATE, field_list=['is_step2_passed'], comment=u'Автоматом: цена есть, галочки не было')
		messages.warning(request, u'Вы уже прошли этот шаг. Теперь вы можете править цены на регистрацию на вкладках отдельных дистанций')
		return redirect(registration.get_editor_url())
	races = event.get_reg_race_set()
	if 'frmRegistration_submit' in request.POST:
		final_prices_are_ok = True # First, we need to have correct final prices
		final_prices = {}
		for race in races:
			price_field_name = 'price_race_{}_finish'.format(race.id)
			if price_field_name not in request.POST:
				messages.warning(request, u'Окончательная цена у дистанции {} не указана. Нужно указать их у всех дистанций'.format(race))
				final_prices_are_ok = False
				break
			cost = models.int_safe(request.POST.get(price_field_name))
			if cost > models.REG_MAX_RACE_COST:
				messages.warning(request, u'Окончательная цена у дистанции {} некорректная. Она не может превышать {} ₽'.format(race, models.REG_MAX_RACE_COST))
				final_prices_are_ok = False
				break
			if (cost < models.REG_MIN_RACE_COST) and (cost != 0):
				messages.warning(request, u'Окончательная цена у дистанции {} некорректная. Она должна быть или нулевой, или не меньше {} ₽'.format(
					race, models.REG_MIN_RACE_COST))
				final_prices_are_ok = False
				break
			final_prices[race.id] = cost

		if final_prices_are_ok:
			col_dates = [None] * N_PRICE_COLS_DEFAULT
			cols_to_use = [False] * N_PRICE_COLS_DEFAULT
			dates_in_cols = set()
			for i in range(N_PRICE_COLS_DEFAULT):
				try:
					col_dates[i] = datetime.datetime.strptime(request.POST.get('price_date_{}'.format(i + 1)), '%Y-%m-%d').date()
					messages.warning(request, u'Распознана дата в столбце {}: {}'.format(i, col_dates[i]))
				except:
					pass
				if col_dates[i]:
					if col_dates[i] in dates_in_cols:
						messages.warning(request, u'Дата {} встречается больше одного раза. Смотрим только на первый столбец'.format(
							col_dates[i].isoformat()))
					elif col_dates[i] == event.finish_date:
						messages.warning(request, u'{} — дата закрытия регистрации. Цены для неё берём из последнего столбца'.format(
							col_dates[i].isoformat()))
					elif col_dates[i] < registration.start_date.date():
						messages.warning(request, u'Дата {} раньше даты открытия регистрации. Игнорируем столбец с ней'.format(
							col_dates[i].isoformat()))
					elif col_dates[i] > registration.finish_date.date():
						messages.warning(request, u'Дата {} позже даты закрытия регистрации. Игнорируем столбец с ней'.format(
							col_dates[i].isoformat()))
					else:
						dates_in_cols.add(col_dates[i])
						cols_to_use[i] = True
			for race in races:
				for i in range(N_PRICE_COLS_DEFAULT):
					cost = models.int_safe(request.POST.get('price_race_{}_date_{}'.format(race.id, i + 1)))
					if not cols_to_use[i]:
						continue
					if cost <= 0:
						continue
					race_cost = models.Race_cost.objects.create(
						race=race,
						finish_date=col_dates[i],
						cost=cost,
						created_by=user,
					)
					models.log_obj_create(user, registration, models.ACTION_RACE_COST_CREATE, child_object=race_cost, comment=u'При создании регистрации')
				race_cost = models.Race_cost.objects.create(
					race=race,
					cost=final_prices[race.id],
					created_by=user,
				)
				models.log_obj_create(user, registration, models.ACTION_RACE_COST_CREATE, child_object=race_cost, comment=u'При создании регистрации')
			
			add_tshirt_question = False
			tshirt_choice = models.int_safe(request.POST.get('tshirts', 0))
			if tshirt_choice == TSHIRT_FREE:
				add_tshirt_question = True
				tshirt_price = 0
			elif tshirt_choice == TSHIRT_FOR_MONEY:
				add_tshirt_question = True
				tshirt_price = models.int_safe(request.POST.get('tshirt_price', 0))
			if add_tshirt_question:
				if tshirt_price > 0:
					question_name = u'Вы можете сразу заказать фирменную футболку соревнований. Стоимость футболке — {} рублей'.format(tshirt_price)
				else:
					question_name = u'Укажите, футболку какого размера вы хотите получить. Стоимость футболки входит в регистрационный взнос'
				question = models.Reg_question.objects.create(
					event=event,
					number=1,
					title=u'Размер футболки',
					name=question_name,
					multiple_answers=False,
					is_required=True,
					created_by=user,
				)
				question.save()
				models.log_obj_create(user, registration, models.ACTION_QUESTION_CREATE, child_object=question, comment=u'При создании регистрации')
				for number, size in enumerate(['XS', 'S', 'M', 'L', 'XL', 'XXL', ]):
					choice = models.Reg_question_choice.objects.create(
						reg_question=question,
						number=number,
						name=size,
						cost=tshirt_price,
						created_by=user,
					)
					models.log_obj_create(user, registration, models.ACTION_QUESTION_CHOICE_CREATE, child_object=choice, comment=u'При создании регистрации')
					for race in races:
						models.Reg_question_race.objects.create(
							reg_question=question,
							race=race,
							added_by=user,
						)
			registration.is_step2_passed = True
			registration.save()
			models.log_obj_create(user, registration, models.ACTION_UPDATE, field_list=['is_step2_passed'], comment=u'При создании регистрации')
			messages.success(request, u'Ура! Регистрация для забега «{}» успешно создана. Теперь вы можете добавить дополнительные вопросы.'.format(event))
			return redirect(registration.get_editor_url())
	context = {}
	context['event'] = event
	context['races'] = races
	context['n_price_cols'] = N_PRICE_COLS_DEFAULT
	context['event'] = event
	return render(request, "editor/registration/reg_create_step2.html", context)

@group_required('admins')
def registration_delete(request, event_id):
	event = get_object_or_404(models.Event, pk=event_id)
	if 'frmDeleteRegistration_submit' in request.POST:
		if not hasattr(event, 'registration'):
			messages.warning(request, u'Регистрация на этот забег ещё не создана')
			return redirect(event)
		registration = event.registration
		messages.success(request, u'Удаляем регистрацию на забег {} с id {}'.format(event, registration.id))
		registration.delete()

		promocodes = models.Promocode.objects.filter(Q(event=event) | Q(race__event=event))
		n_promocodes = promocodes.count()
		if n_promocodes:
			messages.success(request, u'Удаляем {} промокодов'.format(n_promocodes))
			promocodes.delete()

		race_costs = models.Race_cost.objects.filter(race__event=event)
		n_race_costs = race_costs.count()
		if n_race_costs:
			messages.success(request, u'Удаляем {} цен на регистрацию'.format(n_race_costs))
			race_costs.delete()

		race_details = models.Reg_race_details.objects.filter(race__event=event)
		n_race_details = race_details.count()
		if n_race_details:
			messages.success(request, u'Удаляем {} деталей о регистрации на отдельную дистанцию'.format(n_race_details))
			race_details.delete()

		questions = event.reg_question_set.all()
		n_questions = questions.count()
		if n_questions:
			messages.success(request, u'Удаляем {} вопросов'.format(n_questions))
			questions.delete()

		registrants = models.Registrant.objects.filter(race__event=event)
		n_registrants = registrants.count()
		if n_registrants:
			messages.success(request, u'Удаляем {} зарегистрировавшихся'.format(n_registrants))
			registrants.delete()
	return redirect(event)