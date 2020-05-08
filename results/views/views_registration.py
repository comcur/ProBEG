# -*- coding: utf-8 -*-
from __future__ import division
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.contrib import messages
from django.utils import timezone
import datetime

from results import models, forms
from views_common import user_edit_vars

def check_if_reg_is_open(registration, race=None):
	if registration.finish_date < timezone.now():
		return False, u'Онлайн-регистрация на этот забег, к сожалению, закрылась {} в {} по Московскому времени.'.format(
			models.date2str(registration.finish_date.date()), registration.finish_date.strftime("%H:%M"))
	if registration.start_date > timezone.now():
		return False, u'Онлайн-регистрация на этот забег откроется {} в {} по Московскому времени.'.format(
			models.date2str(registration.start_date.date()), registration.start_date.strftime("%H:%M"))
	if race:
		if not hasattr(race, 'reg_race_details'):
			return False, u'Онлайн-регистрация на дистанцию {}, к сожалению, не проводится.'.format(race)
		if not race.reg_race_details.is_open:
			return False, u'Онлайн-регистрация на дистанцию {} в настоящий момент закрыта.'.format(race)
	return True, ''

@login_required
def reg_step1(request, event_id):
	event = get_object_or_404(models.Event, pk=event_id)
	context = user_edit_vars(request.user)
	registration = get_object_or_404(models.Registration, event__id=event_id, is_open=True)

	reg_is_open, message = check_if_reg_is_open(registration)
	if not reg_is_open:
		messages.warning(request, message)
		return redirect(event)
	
	if 'frmRegistrantRace_submit' in request.POST:
		frmRegistrantRace = forms.RegistrantAndRaceForm(request.POST, user=request.user, event=event)
		if frmRegistrantRace.is_valid():
			return redirect('results:reg_step2', race_id=frmRegistrantRace.cleaned_data['race'].id, registrant_id=frmRegistrantRace.cleaned_data['registrant'])
		else:
			messages.warning(request, u"Пожалуйста, заполните все поля в форме.")
	else:
		frmRegistrantRace = forms.RegistrantAndRaceForm(user=request.user, event=event)
	context['frmRegistrantRace'] = frmRegistrantRace
	context['event'] = event
	context['series'] = event.series
	context['registration'] = registration
	context['page_title'] = u'Регистрация на {}. Шаг 1'.format(event.name)
	return render(request, 'registration/reg_step1.html', context)

@login_required
def reg_step2(request, race_id, registrant_id):
	race = get_object_or_404(models.Race, pk=race_id)
	event = race.event
	context = user_edit_vars(request.user)
	registration = get_object_or_404(models.Registration, event__id=event.id, is_open=True)
	registrant_id = models.int_safe(registrant_id)

	reg_is_open, message = check_if_reg_is_open(registration, race)
	if not reg_is_open:
		messages.warning(request, message)
		return redirect(event)

	kwargs = {'registration': registration, 'registrant_id': registrant_id}
	registrant = models.Registrant(race=race, user=request.user, registers_himself=(registrant_id == 0), created_by=request.user)

	if 'frmRegistration_submit' in request.POST:
		frmRegistration = forms.RegistrationForm(request.POST, instance=registrant, **kwargs)
		if frmRegistration.is_valid():
			registrant = frmRegistration.save()
			cleaned_data = frmRegistration.cleaned_data

			if cleaned_data.get('save_registrant_data'):
				saved_registrant = models.Saved_registrant(user=request.user)
				for field in saved_registrant.__class__._meta.get_fields():
					if field.name not in ['id', 'user', 'created_time']:
						try:
							setattr(saved_registrant, field.name, cleaned_data.get(field.name))
						except:
							pass
				saved_registrant.save()
				models.log_obj_create(request.user, saved_registrant, models.ACTION_CREATE, comment=u'При регистрации на забег {} (id {})'.format(
					event, event.id))

			price = registrant.race_cost.cost
			for question in race.get_reg_question_set_for_today():
				field_name = 'question_{}'.format(question.id)
				if question.multiple_answers:
					answers = cleaned_data.get(field_name)
					for answer in answers:
						choice = question.reg_question_choice_set.filter(is_visible=True, pk=answer).first()
						if choice:
							models.Reg_answer.objects.create(registrant=registrant, reg_question_choice=choice, created_by=request.user)
							price += choice.cost
				else:
					answer = cleaned_data.get(field_name)
					if answer:
						choice = question.reg_question_choice_set.filter(is_visible=True, pk=answer).first()
						if choice:
							models.Reg_answer.objects.create(registrant=registrant, reg_question_choice=choice, created_by=request.user)
							price += choice.cost
			registrant.price = price
			registrant.save()
			models.log_obj_create(request.user, registration, models.ACTION_REGISTRANT_CREATE, child_object=registrant, comment=u'При регистрации')
			return redirect('results:reg_step3', race_id=race.id, registrant_id=registrant.id)
		else:
			messages.warning(request, u"Пожалуйста, исправьте ошибки в форме.")
	else:
		frmRegistration = forms.RegistrationForm(instance=registrant, **kwargs)
	context['frmRegistration'] = frmRegistration
	context['event'] = event
	context['race'] = race
	context['registration'] = registration
	context['page_title'] = u'Регистрация на {}. Шаг 2'.format(event.name)
	return render(request, 'registration/reg_step2.html', context)

@login_required
def reg_step3(request, race_id, registrant_id):
	race = get_object_or_404(models.Race, pk=race_id)
	event = race.event
	context = user_edit_vars(request.user)
	registration = get_object_or_404(models.Registration, event__id=event.id, is_open=True)
	registrant_id = models.int_safe(registrant_id)

	reg_is_open, message = check_if_reg_is_open(registration, race)
	if not reg_is_open:
		messages.warning(request, message)
		return redirect(event)

	kwargs = {'registration': registration, 'registrant_id': registrant_id}
	registrant = models.Registrant(race=race, user=request.user, registers_himself=(registrant_id == 0), created_by=request.user)

	if 'frmRegistration_submit' in request.POST:
		frmRegistration = forms.PriceQuestionsForm(request.POST, instance=registrant, **kwargs)
		if frmRegistration.is_valid():
			registrant = frmRegistration.save()
			cleaned_data = frmRegistration.cleaned_data

			if cleaned_data.get('save_registrant_data'):
				saved_registrant = models.Saved_registrant(user=request.user)
				for field in saved_registrant.__class__._meta.get_fields():
					if field.name not in ['id', 'user', 'created_time']:
						try:
							setattr(saved_registrant, field.name, cleaned_data.get(field.name))
						except:
							pass
				saved_registrant.save()
				models.log_obj_create(request.user, saved_registrant, models.ACTION_CREATE, comment=u'При регистрации на забег {} (id {})'.format(
					event, event.id))

			price = registrant.race_cost.cost
			for question in race.get_reg_question_set_for_today():
				field_name = 'question_{}'.format(question.id)
				if question.multiple_answers:
					answers = cleaned_data.get(field_name)
					for answer in answers:
						choice = question.reg_question_choice_set.filter(is_visible=True, pk=answer).first()
						if choice:
							models.Reg_answer.objects.create(registrant=registrant, reg_question_choice=choice, created_by=request.user)
							price += choice.cost
				else:
					answer = cleaned_data.get(field_name)
					if answer:
						choice = question.reg_question_choice_set.filter(is_visible=True, pk=answer).first()
						if choice:
							models.Reg_answer.objects.create(registrant=registrant, reg_question_choice=choice, created_by=request.user)
							price += choice.cost
			registrant.price = price
			registrant.save()
			models.log_obj_create(request.user, registration, models.ACTION_REGISTRANT_CREATE, child_object=registrant, comment=u'При регистрации')
			return redirect('results:reg_cart', registrant_id=registrant.id)
		else:
			messages.warning(request, u"Пожалуйста, исправьте ошибки в форме.")
	else:
		frmRegistration = forms.PriceQuestionsForm(instance=registrant, **kwargs)
	context['frmRegistration'] = frmRegistration
	context['event'] = event
	context['race'] = race
	context['registration'] = registration
	context['page_title'] = u'Регистрация на {}. Шаг 2'.format(event.name)
	return render(request, 'registration/reg_step3.html', context)

@login_required
def reg_cart(request, registrant_id=None):
	context = user_edit_vars(request.user)
	race = None
	if registrant_id:
		registrant = models.Registrant.objects.filter(pk=registrant_id, is_paid=False).first()
		race = registrant.race
	context['registrants'] = request.user.registrant_set.filter(is_paid=False).select_related(
		'race__event__series__city__region__country', 'race__event__city__region__country').order_by(
		'race__event__start_date', 'race__event__name', 'lname')
	context['race'] = race
	context['registrant'] = registrant
	context['page_title'] = u'Оплата регистраций'
	context['total_sum'] = context['registrants'].aggregate(Sum('price'))['price__sum']
	return render(request, 'registration/cart.html', context)

@login_required
def reg_delete(request, registrant_id):
	context = user_edit_vars(request.user)
	if context['is_admin']:
		registrant = get_object_or_404(models.Registrant, pk=registrant_id)
	else:
		registrant = get_object_or_404(models.Registrant, pk=registrant_id, user=request.user)

	race = registrant.race
	event = race.event

	if registrant.is_paid:
		messages.warning(request, u'Регистрация бегуна {} {} на забег {} уже оплачена и не может быть отменена. Придётся бежать!'.format(
			registrant.fname, registrant.lname, race.name_with_event()))
		return redirect(event)

	models.log_obj_create(request.user, event.registration, models.ACTION_REGISTRANT_DELETE, child_object=registrant, comment=u'При отмене регистрации')
	messages.success(request, u'Регистрация бегуна {} {} на забег {} успешно отменена'.format(registrant.fname, registrant.lname, race.name_with_event()))
	registrant.delete()
	return redirect(event)
