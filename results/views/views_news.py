# -*- coding: utf-8 -*-
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from django.db.models import Q

from results import models
from results import forms
from views_common import user_edit_vars, paginate_and_render

def filterNewsByCity(news_list, conditions, city, with_global_news=False):
	q = Q(event__city=city) | Q(event__city_finish=city) | (
		Q(event__city=None) & ( Q(event__series__city=city) | Q(event__series__city_finish=city) )
	)
	if with_global_news:
		q |= Q(event__isnull=True)
	news_list = news_list.filter(q)
	conditions.append(u"в городе " + city.name)
	return news_list, conditions

def filterNewsByRegion(news_list, conditions, region, with_global_news=False):
	q = Q(event__city__region=region) | Q(event__city_finish__region=region) | (
		Q(event__city=None) & ( Q(event__series__city__region=region) | Q(event__series__city_finish__region=region) )
	)
	if with_global_news:
		q |= Q(event__isnull=True)
	news_list = news_list.filter(q)
	conditions.append(u"в регионе " + region.name_full)
	return news_list, conditions

def filterNewsByDistrict(news_list, conditions, district, with_global_news=False):
	q = Q(event__city__region__district=district) | Q(event__city_finish__region__district=district) | (
			Q(event__city=None) &
			(
				Q(event__series__city__region__district=district)
				| Q(event__series__city_finish__region__district=district)
			)
	)
	if with_global_news:
		q |= Q(event__isnull=True)
	news_list = news_list.filter(q)
	conditions.append(u"в федеральном округе " + district.name)
	return news_list, conditions

def filterNewsByCountry(news_list, conditions, country, with_global_news=False):
	q = Q(event__city__region__country=country) | Q(event__city_finish__region__country=country) | (
		Q(event__city=None) &
		( Q(event__series__city__region__country=country) | Q(event__series__city_finish__region__country=country) |
			Q(event__series__country=country)
		)
	)
	if with_global_news:
		q |= Q(event__isnull=True)
	news_list = news_list.filter(q)
	conditions.append(u"в стране " + country.name)
	return news_list, conditions

def all_news(request, country_id=None, region_id=None, city_id=None, one_side=0):
	context = user_edit_vars(request.user)
	list_title = u"Новости"
	conditions = []

	all_news = models.News.objects.select_related('event')
	form = forms.NewsSearchForm()

	country = None
	region = None
	city = None
	initial = {}
	context['short_link_city'] = False
	context['short_link_region'] = False
	context['short_link_country'] = False

	if city_id:
		city = get_object_or_404(models.City, pk=city_id)
		initial['country'] = city.region.country
		if city.region.active:
			initial['region'] = city.region
		form = forms.NewsSearchForm(initial=initial)
		context['city'] = city
		context['short_link_city'] = True
	elif region_id:
		region = get_object_or_404(models.Region, pk=region_id)
		form = forms.NewsSearchForm(initial={'region': region})
		context['short_link_region'] = True
	elif country_id:
		country = get_object_or_404(models.Country, pk=country_id)
		form = forms.NewsSearchForm(initial={'country': country})
		context['short_link_country'] = True
	elif (request.method == 'GET') and ('frmSearchNews_submit' in request.GET) or ('page' in request.GET):
		form = forms.NewsSearchForm(request.GET)
		if form.is_valid():
			country = form.cleaned_data['country']
			region = form.cleaned_data['region']
			city = form.cleaned_data['city']

			news_text = form.cleaned_data['news_text']
			if news_text:
				all_news = all_news.filter(Q(title__icontains=news_text) | Q(content__icontains=news_text))
				conditions.append(u"с «{}» в названии или тексте".format(news_text))
			date_from = form.cleaned_data['date_from']
			if date_from:
				all_news = all_news.filter(date_posted__gte=date_from)
				conditions.append(u"не раньше {}".format(date_from.isoformat()))
			date_to = form.cleaned_data['date_to']
			if date_to:
				all_news = all_news.filter(date_posted__lte=date_to)
				conditions.append(u"не позже {}".format(date_to.isoformat()))
			published_by_me = form.cleaned_data['published_by_me']
			if published_by_me:
				all_news = all_news.filter(created_by=request.user)
				conditions.append(u"с автором – мной")

			if (not published_by_me) and (not news_text) and (not date_from) and (not date_to):
				if city_id:
					context['short_link_city'] = True
				elif region:
					context['short_link_region'] = True
				elif country:
					context['short_link_country'] = True

	if country:
		all_news, conditions = filterNewsByCountry(all_news, conditions, country)
	if region:
		all_news, conditions = filterNewsByRegion(all_news, conditions, region)
	if city:
		all_news, conditions = filterNewsByCity(all_news, conditions, city)

	if not context['is_admin']:
		all_news = all_news.filter(is_for_social=False)
	all_news = all_news.order_by('-date_posted')
	context['form'] = form
	context['country'] = country
	context['region'] = region
	context['city'] = city
	context['one_side'] = one_side
	context['list_title'] = list_title + " " + ", ".join(conditions)

	return paginate_and_render(request, 'results/news.html', context, all_news)

def news_details(request, news_id=None):
	news = get_object_or_404(models.News, pk=news_id)
	context = user_edit_vars(request.user)
	context['news'] = news
	context['page_title'] = news.title
	if context['is_admin']:
		context['social_pages'] = models.Social_page.objects.filter(district__isnull=True)
		# context['posts'] = models.Social_news_post.objects.filter(news=news).order_by('-date_posted')
	else:
		news.n_views += 1
		news.save()
	return render(request, 'results/news_details.html', context)
