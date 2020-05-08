# -*- coding: utf-8 -*-
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db.models import Q
import datetime

from results.views.views_user import home
from editor.views.views_stat import get_stat_value
from results import models
from . import forms

def register_view(request, context={}):
	if request.user.is_authenticated:
		return home(request)

	if request.method != 'POST':
		return login_view(request)

	form = forms.RegisterForm(request.POST)
	context['registerForm'] = form
	if not form.is_valid():
		return login_view(request, context)

	lname = form.cleaned_data['reg_lname'].strip()
	fname = form.cleaned_data['reg_fname'].strip()
	email = form.cleaned_data['reg_email'].strip()
	password = form.cleaned_data['reg_password']
	password_confirm = form.cleaned_data['reg_password_confirm']

	if lname == "":
		context['msgErrorRegister'] = u"Вы не указали фамилию. Попробуйте ещё раз."
		return login_view(request, context)

	if lname == "":
		context['msgErrorRegister'] = u"Вы не указали имя. Попробуйте ещё раз."
		return login_view(request, context)

	if password != password_confirm:
		context['msgErrorRegister'] = u"Введённые пароли не совпадают. Попробуйте ещё раз."
		return login_view(request, context)

	if User.objects.filter(username=email).count() > 0:
		context['msgErrorRegister'] = u"Пользователь с таким адресом электронной почты уже зарегистрирован."
		return login_view(request, context)

	user = User.objects.create_user(email, email, password)
	user.first_name = fname
	user.last_name = lname
	user.save()
	
	user = authenticate(username=email, password=password)
	login(request, user)

	return redirect("results:my_details")

def login_view(request, context={}):
	LOGIN_TEMPLATE = 'probeg_auth/login2.html'
	#if request.user.is_authenticated:
	#	return home(request)

	context['skip_adsense'] = True

	if 'next' in request.GET:
		context['next_page_suffix'] = u'?next={}'.format(request.GET.get('next'))

	context['loginForm'] = forms.LoginForm()
	if 'registerForm' not in context:
		context['registerForm'] = forms.RegisterForm()

	context['n_events_in_past'] = get_stat_value('n_events_in_past')
	context['n_events_in_future'] = get_stat_value('n_events_in_future')
	context['n_events_this_month_RU_UA_BY'] = get_stat_value('n_events_this_month_RU_UA_BY')
	context['n_results'] = get_stat_value('n_results')
	context['n_results_with_runner'] = get_stat_value('n_results_with_runner')
	if 'email' not in request.POST:
		return render(request, LOGIN_TEMPLATE, context=context)

	form = forms.LoginForm(request.POST) if (request.method == 'POST') else forms.LoginForm()
	context['loginForm'] = form
	if (request.method != 'POST') or not form.is_valid():
		return render(request, LOGIN_TEMPLATE, context=context)

	email = form.cleaned_data['email']
	password = form.cleaned_data['password']
	user = authenticate(username=email, password=password)

	if user is not None:
		if user.is_active:
			login(request, user)
			return redirect("results:home")
		else:
			context['msgError'] = u"Этот пользователь неактивен. Пожалуйста, обратитесь к администраторам, если нужно это исправить."
			return render(request, LOGIN_TEMPLATE, context=context)
	elif request.method == 'POST':
		context['msgError'] = u"Такой пользователь не зарегистрирован, либо же Вы ошиблись в логине или пароле."
	return render(request, LOGIN_TEMPLATE, context=context)
