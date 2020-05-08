# -*- coding: utf-8 -*-
from django.shortcuts import render, redirect, get_object_or_404
from django.forms import modelformset_factory
from django.core.urlresolvers import reverse
from django.db.models.query import Prefetch
from django.contrib import messages
from django.conf import settings
from twython import Twython
import facebook
import requests
import datetime
import json
import vk

from results import models
from editor import forms
from .views_common import group_required
from .views_user_actions import log_document_formset

TWITTER_MAX_IMAGE_SIZE = 3145728

def write_log(s):
	f = open(models.LOG_FILE_SOCIAL, "a")
	try:
		f.write(datetime.datetime.today().isoformat(' ') + " " + s + "\n")
	except:
		f.write(datetime.datetime.today().isoformat(' ') + " " + s.encode('utf-8') + "\n")
	f.close()
	return s

def post_to_fb(page, message, image_url='', link='', link_name='', caption=''):
	graph = facebook.GraphAPI(page.access_token)
	attachment = None
	if image_url or link:
		attachment =  {
			'name': link_name,
			'link': link,
			'caption': caption,
			'picture': image_url,
		}
	response = graph.put_wall_post(message=message, attachment=attachment)
	return response

def post_to_vk(page, message, image_path='', link=''):
	session = vk.Session(access_token=page.access_token)
	api = vk.API(session, v="5.54") # version parameter added on 2018-03-05
	attachments = []
	if image_path:
		upload_server = api.photos.getWallUploadServer(group_id=page.page_id)
		write_log('photos.getWallUploadServer with group_id {}: {}'.format(page.page_id, upload_server))
		upload_url = upload_server['upload_url']
		album_id = upload_server['album_id'] # Was 'aid' until 2018-03-05
		img = {'photo': (image_path.split('/')[-1], open(image_path, 'rb'))}
		image_response = requests.post(upload_url, files=img)
		server_result = json.loads(image_response.text)
		write_log('requests.post with upload_url {} and image {}: {}'.format(upload_url, image_path, server_result))

		# Сохраняем фото на сервере и получаем id
		photo_save_response = api.photos.saveWallPhoto(group_id=page.page_id,
			photo=server_result['photo'], hash=server_result['hash'], server=server_result['server'])
		write_log('photos.saveWallPhoto with group_id {}: {}'.format(page.page_id, photo_save_response))

		# Теперь этот id остается лишь прикрепить в attachments метода wall.post
		attachments.append(unicode(photo_save_response[0]['id']))
	if link:
		attachments.append(link)
	post_response = api.wall.post(message=message, owner_id='-' + page.page_id, attachments=','.join(attachments))
	write_log('wall.post with owner_id {}: {}'.format('-' + page.page_id, post_response))
	return post_response.get('post_id', '')

def post_to_twitter(page, message, image_path='', link=''):
	twitter = Twython(settings.SOCIAL_AUTH_TWITTER_KEY, settings.SOCIAL_AUTH_TWITTER_SECRET,
		page.access_token, page.token_secret)
	if image_path:
		# photo = open(image_path, 'rb')
		with open(image_path, 'rb') as photo:
			response = twitter.upload_media(media=photo)
			media_ids=[response['media_id']]
	else:
		media_ids = None
	status = message[:116]
	if link:
		status += ' ' + link
	write_log(u'{} Tweeting to page {}: photo {}, status {}, media_id {}'.format(
			datetime.datetime.now(), page.name, image_path, status, media_ids[0] if media_ids else ''))
	res = twitter.update_status(status=status, media_ids=media_ids)
	write_log(u'{} Twitter post_id: {}'.format(
			datetime.datetime.now(), res['id_str']))
	return res, status

def post_news(request, page, news, tweet):
	try:
		if page.page_type == models.SOCIAL_TYPE_TWITTER:
			if tweet.strip() == '':
				return False, u'Для постов в твиттер нужно указать текст в отдельном поле'
			message = tweet
		else:
			message = news.title + '\n\n' + news.plain_content()
		if news.is_for_social and news.event:
			# link = news.event.series.get_old_url()
			link = models.SITE_URL + news.event.get_absolute_url()
		elif not news.is_for_social:
			# link = news.get_old_url()
			link = models.SITE_URL + news.get_absolute_url()
		else:
			link = ''
		tweet = ''
		if page.page_type == models.SOCIAL_TYPE_FB:
			result = post_to_fb(page, message,
				image_url=news.image.url if news.image else '',
				link=link,
				link_name=news.event.name if news.event else news.title,
				caption=news.event.date() if news.event else '')
			post_id = result['id'].split('_')[1]
		elif page.page_type == models.SOCIAL_TYPE_VK:
			result = post_to_vk(page, message,
				image_path=news.image.path if news.image else '',
				link=link)
			post_id = result
		elif page.page_type == models.SOCIAL_TYPE_TWITTER:
			if news.image and news.image_size() <= TWITTER_MAX_IMAGE_SIZE:
				image_path = news.image.path
			else:
				image_path = ''
			result, tweet = post_to_twitter(page, message, image_path=news.image.path if news.image else '', link=link)
			post_id = result['id_str']
		post = models.Social_news_post.objects.create(news=news, social_page=page, post_id=post_id,
			created_by=request.user, tweet=tweet)
		models.Table_update.objects.create(model_name='Social_page', row_id=page.id, child_id=news.id, user=request.user,
			action_type=models.ACTION_SOCIAL_POST, is_verified=request.user.groups.filter(name="admins").exists())
		return True, post
	except Exception as e:
		write_log('{} Error while posting news {} to page {}: {}'.format(
			datetime.datetime.now(), news.id, page.id, repr(e)))
		return False, repr(e)

N_EXTRA_PAGES = 3
def getSocialPageFormSet(data=None):
	SocialPageFormSet = modelformset_factory(models.Social_page, form=forms.SocialPageForm, can_delete=True, extra=N_EXTRA_PAGES)
	return SocialPageFormSet(
		data=data,
		queryset=models.Social_page.objects.order_by('page_type', 'name')
	)

@group_required('admins')
def social_pages(request):
	context = {}
	if (request.method == 'POST') and request.POST.get('frmSocialPages_submit', False):
		formset = getSocialPageFormSet(data=request.POST)
		if formset.is_valid():
			formset.save()
			log_document_formset(request.user, None, formset)
			messages.success(request, (u'Страницы в соцсетях обновлены: {} страниц добавлено, {} обновлено, '
				+ u'{} удалено. Проверьте, всё ли правильно.').format(
				len(formset.new_objects), len(formset.changed_objects), len(formset.deleted_objects)))
			return redirect('editor:social_pages')
		else:
			messages.warning(request, u"Страницы в соцсетях не обновлены. Пожалуйста, исправьте ошибки в форме.")
	else:
		formset = getSocialPageFormSet()
	context['frmSocialPages'] = formset
	context['page_title'] = u'Наши страницы в социальных сетях'
	return render(request, "editor/social_pages.html", context)

@group_required('admins')
def social_page_history(request, page_id):
	page = get_object_or_404(models.Social_page, pk=page_id)
	context = {}
	context['is_admin'] = True
	context['changes'] = models.Table_update.objects.filter(model_name='Social_page', row_id=page.id).select_related(
		'user').prefetch_related(Prefetch('field_update_set',
		queryset=models.Field_update.objects.order_by('field_name'))).order_by('-added_time')
	context['obj_link'] = reverse('editor:social_pages') # TODO: page about social page

	context['page_title'] = u'{} (id {}): история изменений'.format(page, page.id)
	
	return render(request, "editor/changes_history.html", context)
