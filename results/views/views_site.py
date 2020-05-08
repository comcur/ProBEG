# -*- coding: utf-8 -*-
from __future__ import division
from django.core.urlresolvers import reverse
from django.shortcuts import render

import datetime

from views_common import user_edit_vars
from editor.views.views_stat import get_stat_value
from editor.views.views_common import group_required
from results import models

def about(request):
	context = {}
	context['page_title'] = u'О сайте'
	return render(request, "results/about.html", context)

def about_new_site(request):
	context = {}
	context['page_title'] = u'О новом разделе сайта'
	return render(request, "results/about_new_site.html", context)

def contacts(request):
	context = {}
	context['page_title'] = u'Контактная информация'
	return render(request, "results/contacts.html", context)

def protocol(request):
	context = {}
	context['page_title'] = u'Стандарт протокола'
	return render(request, "results/protocol.html", context)

def social_links(request):
	context = {}
	context['page_title'] = u'ПроБЕГ в социальных сетях'
	return render(request, "results/social_links.html", context)

def how_to_help(request):
	context = {}
	context['page_title'] = u'Как вы можете помочь сайту «ПроБЕГ»'
	return render(request, "results/how_to_help.html", context)

def add_new_event(request):
	context = {}
	context['page_title'] = u'Как добавить новый забег в календарь на сайте «ПроБЕГ»?'
	context['user_is_authenticated'] = request.user.is_authenticated
	return render(request, "results/add_new_event.html", context)

# def best_russian_races_2017(request):
# 	context = {}
# 	context['page_title'] = u'Самые заметные забеги в России в 2017 году'
# 	return render(request, "articles/best_russian_races_2017.html", context)

def sport_classes(request):
	context = {}
	context['page_title'] = u'Разрядные нормативы в беге в России'
	return render(request, "static/sport_classes.html", context)

def measurement_about(request):
	context = {}
	context['page_title'] = u'Сертификация трасс'
	return render(request, "measurement/about.html", context)

def login_problems(request):
	context = {}
	context['page_title'] = u'Частые проблемы при авторизации на нашем сайте'
	return render(request, "results/login_problems.html", context)

def archive(request):
	context = {}
	context['page_title'] = u'Архивные документы'
	return render(request, "results/archive.html", context)

def results_binding(request):
	context = {}
	context['page_title'] = u'О привязке результатов'
	context['n_results'] = get_stat_value('n_results')
	# context['n_results_from_ak'] = get_stat_value('n_results_from_ak')
	context['n_results_from_klb'] = get_stat_value('n_results_from_klb')
	context['n_results_from_parkrun'] = get_stat_value('n_results_from_parkrun')
	context['n_results_with_user'] = get_stat_value('n_results_with_user')
	return render(request, "results/results_binding.html", context)

N_FIRST_TEAMS = 3
N_FIRST_PERSONS = 10
N_FIRST_NEWS = 29
def main_page(request):
	context = user_edit_vars(request.user)
	context['all_news'] = models.News.objects.select_related(
		'event__city__region__country', 'event__series__city__region__country', 'event__series__city_finish__region__country').filter(
		is_for_social=False).order_by('-date_posted')[:N_FIRST_NEWS]
	context['is_authenticated'] = request.user.is_authenticated

	today = datetime.date.today()
	year = today.year if (today.month > 1 or today.day > 16) else (today.year - 1)
	if not models.is_active_klb_year(year):
		year = models.CUR_KLB_YEAR

	teams = models.Klb_team.objects.filter(year=year).exclude(number=models.INDIVIDUAL_RUNNERS_CLUB_NUMBER).select_related('club__city__region__country')

	context['year'] = year
	context['klb_categories'] = []
	context['klb_categories'].append({
		'name': u'Абсолютный зачёт',
		'teams': teams.order_by('place', 'name')[:N_FIRST_TEAMS],
		'link': reverse('results:klb_match_summary', kwargs={'tab': 'all'}),
	})
	context['klb_categories'].append({
		'name': u'Средние клубы',
		'teams': teams.filter(place_medium_teams__isnull=False).order_by('place_medium_teams', 'name')[:N_FIRST_TEAMS],
		'link': reverse('results:klb_match_summary', kwargs={'tab': 'medium'}),
	})
	context['klb_categories'].append({
		'name': u'Малые клубы',
		'teams': teams.filter(place_small_teams__isnull=False).order_by('place_small_teams', 'name')[:N_FIRST_TEAMS],
		'link': reverse('results:klb_match_summary', kwargs={'tab': 'small'}),
	})

	context['participants'] = models.Klb_participant.objects.filter(match_year=year, place__isnull=False, n_starts__gt=0).order_by('place').select_related(
		'klb_person__city__region__country', 'team')[:N_FIRST_PERSONS]
	context['absolute_table_link'] = models.Klb_age_group.objects.get(match_year=year, gender=models.GENDER_UNKNOWN).get_absolute_url()

	if not context['is_authenticated']:
		context['n_events_in_past'] = get_stat_value('n_events_in_past')
		context['n_events_in_future'] = get_stat_value('n_events_in_future')
		# context['n_events_this_week'] = get_stat_value('n_events_this_week')
		context['n_events_this_month_RU_UA_BY'] = get_stat_value('n_events_this_month_RU_UA_BY')
		context['n_results'] = get_stat_value('n_results')
		context['n_results_with_runner'] = get_stat_value('n_results_with_runner')
	return render(request, 'results/main_page.html', context=context)
