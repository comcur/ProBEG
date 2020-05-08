# -*- coding: utf-8 -*-
from django.shortcuts import get_object_or_404, render, redirect

from results import models
from editor.forms import UsefulLabelForm, UsefulLinkForm
from .views_common import user_edit_vars

def useful_links(request):
	context = user_edit_vars(user)
	context['page_title'] = u'Полезные ссылки'
	context['links_by_label'] = models.Useful_label.objects.prefetch_related('useful_link_set')
	if context['is_admin']:
		context['frmNewLink'] = UsefulLinkForm()
		context['frmNewLabel'] = UsefulLabelForm()

	return render(request, 'results/useful_links.html', context)
