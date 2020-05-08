# -*- coding: UTF-8 -*-

from __future__ import unicode_literals
from urlparse import parse_qs
import webbrowser
import vk

# id of vk.com application
APP_ID = '5549184' # '5410674'

def get_auth_params():
    auth_url = ("https://oauth.vk.com/authorize?client_id={app_id}"
                "&scope=wall&redirect_uri=http://oauth.vk.com/blank.html"
                "&display=page&response_type=token".format(app_id=APP_ID))
    webbrowser.open_new_tab(auth_url)
    redirected_url = input("Paste here url you were redirected:\n")
    aup = parse_qs(redirected_url)
    aup['access_token'] = aup.pop(
        'https://oauth.vk.com/blank.html#access_token')
    print "Token: {}, expires in {}, user_id: {}".format(aup['access_token'][0], aup['expires_in'][0],
                     aup['user_id'][0])
    return aup['access_token'][0], aup['user_id'][0]


def get_api(access_token):
    session = vk.Session(access_token=access_token)
    return vk.API(session)

def main():
    access_token, _ = get_auth_params()
    api = get_api(access_token)

main()