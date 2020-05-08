# -*- coding: utf-8 -*-
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from django.db.models import Q, F, Sum, Count
import datetime
import re

from results import models
from results import forms
from views_common import user_edit_vars, paginate_and_render, get_filtered_results_dict, get_lists_for_club_membership
from editor.views.views_common import group_required

def runners(request, lname='', fname=''):
	context = user_edit_vars(request.user)
	# runners = models.Runner.objects.select_related('klb_person', 'user__user_profile', 'ak_person').annotate(
	# 	Count('result')).order_by('lname', 'fname')
	runners = models.Runner.objects.select_related('user__user_profile', 'city__region__country')
	if not context['is_admin']:
		runners = runners.filter(n_starts__gt=0)
	list_title = u"Участники забегов"
	conditions = []
	initial = {}
	ordering = 'length_cur_year' # 'finishes_cur_year'
	form = None

	lname = lname.strip()
	fname = fname.strip()
	if lname or fname:
		initial['lname'] = lname
		initial['fname'] = fname
	elif any(s in request.GET for s in ['btnSearchSubmit', 'page', 'ordering']):
		form = forms.RunnerForm(request.GET)
		if form.is_valid():
			lname = form.cleaned_data['lname'].strip()
			fname = form.cleaned_data['fname'].strip()

			birthday_from = form.cleaned_data['birthday_from']
			if birthday_from:
				runners = runners.filter(Q(birthday_known=True, birthday__gte=birthday_from)
					| Q(birthday_known=False, birthday__year__gt=birthday_from.year))
				conditions.append(u"с датой рождения не раньше " + birthday_from.isoformat())

			birthday_to = form.cleaned_data['birthday_to']
			if birthday_to:
				runners = runners.filter(Q(birthday_known=True, birthday__lte=birthday_to)
					| Q(birthday_known=False, birthday__year__lt=birthday_to.year))
				conditions.append(u"с датой рождения не позже " + birthday_to.isoformat())

			if context['is_admin']:
				if form.cleaned_data['is_in_klb']:
					runners = runners.filter(klb_person__isnull=False)
					conditions.append(u"участвовавшие в КЛБМатчах")

				if form.cleaned_data['is_user']:
					if context['is_admin']:
						runners = runners.filter(user__isnull=False)
					else:
						runners = runners.filter(user__user_profile__is_public=True)
					list_title += u", зарегистрированные на сайте"

				# if form.cleaned_data['is_ak_person']:
				# 	runners = runners.filter(ak_person__isnull=False)
				# 	conditions.append(u"из базы АК55")

				if form.cleaned_data['is_in_parkrun']:
					runners = runners.filter(parkrun_id__isnull=False)
					conditions.append(u"участвовавшие в паркранах")
			else:
				runners = runners.filter(private_data_hidden=False)
			if 'ordering' in request.GET:
				ordering = request.GET['ordering']
	if form is None:
		form = forms.RunnerForm(initial=initial)

	lname = lname.replace('/', '')
	fname = fname.replace('/', '')
	if lname and fname:
		runners = runners.filter(Q(lname__istartswith=lname, fname__istartswith=fname) | Q(lname__istartswith=fname, fname__istartswith=lname))
		conditions.append(u"с фамилией «" + lname + u"*»")
		conditions.append(u"с именем «" + fname + u"*»")
	elif lname:
		runners = runners.filter(lname__istartswith=lname)
		conditions.append(u"с фамилией «" + lname + u"*»")
	elif fname:
		runners = runners.filter(fname__istartswith=fname)
		conditions.append(u"с именем «" + fname + u"*»")

	ordering_list = []
	if ordering == 'finishes_all':
		ordering_list.append('-n_starts')
	elif ordering == 'length_all':
		ordering_list.append('-total_length')
	elif ordering == 'time_all':
		ordering_list.append('-total_time')
	elif ordering == 'finishes_cur_year':
		ordering_list.append('-n_starts_{}'.format(models.CUR_RUNNERS_ORDERING_YEAR))
	elif ordering == 'length_cur_year':
		ordering_list.append('-total_length_{}'.format(models.CUR_RUNNERS_ORDERING_YEAR))
	elif ordering == 'time_cur_year':
		ordering_list.append('-total_time_{}'.format(models.CUR_RUNNERS_ORDERING_YEAR))
	elif ordering == 'name':
		ordering_list.append('lname')
		ordering_list.append('fname')
	elif ordering == 'city':
		ordering_list.append('city__name')
	elif ordering == 'birthday':
		ordering_list.append('birthday')
		# runners = runners.exclude(birthday=None)
	for x in ['lname', 'fname']:
		if x not in ordering_list:
			ordering_list.append(x)
	runners = runners.order_by(*ordering_list)

	context['list_title'] = list_title + " " + ", ".join(conditions)
	context['form'] = form
	context['page_title'] = u'Поиск по участникам забегов'
	context['ordering'] = ordering
	context['lname'] = lname
	context['fname'] = fname
	context['cur_stat_year'] = models.CUR_RUNNERS_ORDERING_YEAR
	return paginate_and_render(request, 'results/runners.html', context, runners)

def runner_details_full(request, runner_id):
	return runner_details(request, runner_id, show_full_page=True)

def runner_details(request, runner_id, show_full_page=False):
	runner = get_object_or_404(models.Runner, pk=runner_id)
	context = user_edit_vars(request.user)
	klb_person = runner.klb_person
	# ak_person = runner.ak_person
	user = runner.user
	context['runner'] = runner

	context.update(get_filtered_results_dict(request, runner, runner.has_many_distances, klb_person is not None, show_full_page))
	context.update(get_lists_for_club_membership(request.user, runner, context['is_admin']))
	if klb_person:
		context['klb_person'] = klb_person
		context['n_klb_results'] = klb_person.klb_result_set.count()
	runner_name = u'{} {}'.format(runner.fname, runner.lname) if (context['is_admin'] or not runner.private_data_hidden) else u'(имя скрыто)'
	context['page_title'] = u'{}: все результаты'.format(runner_name)

	return render(request, 'results/runner_details.html', context)
