# -*- coding: utf-8 -*-
from django.shortcuts import get_object_or_404, render, redirect

def parkrun_stat(request):
	context = {}
	context['page_title'] = u'Статистика по паркранам России'
	context['authenticated'] = request.user.is_authenticated
	return render(request, 'results/parkrun_stat.html', context)
