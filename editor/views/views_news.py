# -*- coding: utf-8 -*-
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import permission_required
from django.core.files.temp import NamedTemporaryFile
from django.core.urlresolvers import reverse
from django.db.models.query import Prefetch
from django.contrib import messages
from django.core.files import File

from results import models
from results.views.views_common import paginate_and_render, user_edit_vars
from editor import forms
from .views_user_actions import log_form_change
from .views_common import group_required, check_rights, changes_history
from .views_social import post_news

@group_required('admins')
def news_details(request, news_id=None, news=None, cloned_news_id=None, frmNews=None, create_new=False):
	if not news: # False if we are creating new news
		news = get_object_or_404(models.News, pk=news_id)

	if news and not frmNews:
		# initial = {}
		# if news.city:
		# 	initial['city'] = news.city
		# 	initial['region'] = news.city.region
		# 	initial['country'] = news.city.region.country
		# elif news.country:
		# 	initial['country'] = news.country
		# frmNews = forms.NewsForm(instance=news, initial=initial)
		frmNews = forms.NewsForm(instance=news)

	context = {}
	context['news'] = news
	context['frmNews'] = frmNews
	context['create_new'] = create_new
	context['cloned_news_id'] = cloned_news_id

	if cloned_news_id:
		context['page_title'] = u'Клонирование новости'
	elif create_new:
		context['page_title'] = u'Создание новой новости'
	else:
		context['page_title'] = u'Новость «{}» (id {})'.format(news, news.id)
	return render(request, "editor/news_details.html", context)

@group_required('admins')
def news_changes_history(request, news_id):
	news = get_object_or_404(models.News, pk=news_id)
	context = user_edit_vars(request.user)
	return changes_history(request, context, news, news.get_absolute_url())

@group_required('admins')
def news_update(request, news_id):
	news = get_object_or_404(models.News, pk=news_id)
	if (request.method == 'POST') and request.POST.get('frmNews_submit', False):
		form = forms.NewsForm(request.POST, request.FILES, instance=news)
		if form.is_valid():
			form.save()
			log_form_change(request.user, form, action=models.ACTION_UPDATE, exclude=['country', 'region'])
			messages.success(request, u'Новость «{}» успешно обновлена. Проверьте, всё ли правильно.'.format(news))
			if 'image' in form.changed_data:
				news.refresh_from_db()
				if not news.make_thumbnail():
					messages.warning(request, u"Не получилось уменьшить фото для новости с id {}.".format(news.id))
			return redirect(news.get_editor_url())
		else:
			messages.warning(request, u"Новость не обновлена. Пожалуйста, исправьте ошибки в форме.")
	else:
		form = forms.NewsForm(instance=news)
	return news_details(request, news_id=news_id, news=news, frmNews=form)

@group_required('admins')
def news_create(request, country_id=None, region_id=None, city_id=None, news_id=None):
	if news_id: # Clone news with this id
		news = get_object_or_404(models.News, pk=news_id)
		news.id = None
		news.date_posted = datetime.datetime.now()
	else:
		news = models.News()
	news.created_by = request.user
	if (request.method == 'POST') and request.POST.get('frmNews_submit', False):
		form = forms.NewsForm(request.POST, request.FILES, instance=news)
		if form.is_valid():
			form.save()
			log_form_change(request.user, form, action=models.ACTION_CREATE, exclude=['country', 'region'])
			if news.image:
				if not news.make_thumbnail():
					messages.warning(request, u"Не получилось уменьшить фото для новости с id {}.".format(news.id))
			messages.success(request, u'Новость «{}» успешно создана. Проверьте, всё ли правильно.'.format(news))
			return redirect(news.get_editor_url())
		else:
			messages.warning(request, u"Новость не создана. Пожалуйста, исправьте ошибки в форме.")
	else:
		initial = {}
		# if country_id:
		# 	initial['country'] = get_object_or_404(Country, pk=country_id)
		# if region_id:
		# 	initial['region'] = get_object_or_404(Region, pk=region_id)
		# 	initial['country'] = initial['region'].country
		# if city_id:
		# 	city = get_object_or_404(City, pk=city_id)
		# 	news.city = city
		# 	initial['city'] = city
		# 	if city.region.active:
		# 		initial['region'] = city.region
		# 	else:
		# 		initial['country'] = city.region.country
		form = forms.NewsForm(instance=news, initial=initial)

	return news_details(request, news=news, frmNews=form, create_new=True, cloned_news_id=news_id)

@group_required('admins')
def news_delete(request, news_id):
	news = get_object_or_404(models.News, pk=news_id)
	ok_to_delete = False

	if (request.method == 'POST') and request.POST.get('frmDeleteNews_submit', False):
		models.log_obj_delete(request.user, news)
		news.delete()
		messages.success(request, u'Новость «{}» успешно удалена.'.format(news))
		return redirect('results:all_news')
	return news_details(request, news_id=news_id, news=news)

@group_required('editors', 'admins')
def news_post(request, news_id=None):
	news = get_object_or_404(models.News, pk=news_id)
	context, has_rights, target = check_rights(request, event=news.event)
	if not has_rights:
		return target
	news_posted = 0
	if request.method == 'POST':
		tweet = request.POST['twitter_text']
		for page in models.Social_page.objects.all():
			if 'page_' + str(page.id) in request.POST:
				result, post = post_news(request, page, news, tweet)
				if result:
					news_posted += 1
				else:
					messages.warning(request, u'Ошибка с публикацией в группу {}. Текст ошибки: {}'.format(page.url, post))
		if news_posted:
			messages.success(request, u'Опубликовано новостей: {}'.format(news_posted))
	if news.event:
		return redirect("results:event_details", event_id=news.event.id)
	else:
		return redirect("results:news_details", news_id=news.id)
