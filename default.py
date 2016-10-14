# -*- coding: utf-8 -*-
"""
A Kodi plugin for ESPN Player
"""
import sys
import os
import urllib
import urlparse
from datetime import datetime

from resources.lib.fslib import fslib

import xbmc
import xbmcaddon
import xbmcvfs
import xbmcgui
import xbmcplugin

addon = xbmcaddon.Addon()
addon_path = xbmc.translatePath(addon.getAddonInfo('path'))
addon_profile = xbmc.translatePath(addon.getAddonInfo('profile'))
language = addon.getLocalizedString
logging_prefix = '[%s-%s]' % (addon.getAddonInfo('id'), addon.getAddonInfo('version'))

if not xbmcvfs.exists(addon_profile):
    xbmcvfs.mkdir(addon_profile)

_url = sys.argv[0]  # get the plugin url in plugin:// notation
_handle = int(sys.argv[1])  # get the plugin handle as an integer number

cookie_file = os.path.join(addon_profile, 'cookie_file')
credentials_file = os.path.join(addon_profile, 'credentials')

if addon.getSetting('debug') == 'false':
    debug = False
else:
    debug = True

if addon.getSetting('verify_ssl') == 'false':
    verify_ssl = False
else:
    verify_ssl = True

fs = fslib(cookie_file, credentials_file, debug, verify_ssl)


def addon_log(string):
    if debug:
        xbmc.log('%s: %s' % (logging_prefix, string))


def play_video(channel_id, airing_id):
    stream_url = fs.get_stream_url(channel_id, airing_id)
    if stream_url:
        bitrate = select_bitrate(stream_url['bitrates'].keys())
        if bitrate:
            play_url = stream_url['bitrates'][bitrate]
            playitem = xbmcgui.ListItem(path=play_url)
            playitem.setProperty('IsPlayable', 'true')
            xbmcplugin.setResolvedUrl(_handle, True, listitem=playitem)
    else:
        dialog = xbmcgui.Dialog()
        dialog.ok(language(30020), language(30021))
        
def main_menu():
    items = [language(30023), language(30015), language(30026), language(30030)]
    for item in items:
        if item == language(30023):
            now = datetime.now()
            date_today = now.date()
            parameters = {
                'action': 'list_events_by_date',
                'schedule_type': 'all',
                'filter_date': date_today
            }
        elif item == language(30015):
           parameters = {'action': 'list_event_dates'}
        elif item == language(30026):
            parameters = {
                'action': 'list_events',
                'schedule_type': 'featured'
            }
        else:  # auth details
            item = '[B]%s[/B]' % item
            parameters = {'action': 'show_auth_details'}
        add_item(item, parameters)
    xbmcplugin.endOfDirectory(_handle)
    
def coloring(text, meaning):
    """Return the text wrapped in appropriate color markup."""
    if meaning == 'channel':
        color = 'FF0FE8F0'
    elif meaning == 'live':
        color = 'FF03F12F'
    elif meaning == 'upcoming':
        color = 'FFF16C00'
    elif meaning == 'replay':
        color = 'FFE71A2B'
    colored_text = '[COLOR=%s]%s[/COLOR]' % (color, text)
    return colored_text
    

def list_events(schedule_type, filter_date=False):
    items = []
    now = datetime.now()
    date_today = now.date()
    
    if addon.getSetting('show_deportes') == 'true':
        deportes = True
    else:
        deportes = False
    
    schedule = fs.get_schedule(schedule_type, filter_date=filter_date, deportes=deportes)
    
    for event in schedule:
        channel_id = event['airings'][0]['channel_id']
        airing_id = event['airings'][0]['airing_id']
        channel_name = event['airings'][0]['channel_name']
        airing_date_obj = fs.parse_datetime(event['airings'][0]['airing_date'], localize=True)
        airing_date = airing_date_obj.date()
                          
        try:
            sport_tag = event['sport_tag']
        except KeyError:
            sport_tag = None
            
        if addon.getSetting('time_notation') == '0':  # 12 hour clock
            time = airing_date_obj.strftime('%I:%M %p')
        else:
            time = airing_date_obj.strftime('%H:%M')
            
        if airing_date == date_today:
            start_time = '%s %s' % (language(30023), time)
        else:
            start_time = '%s %s' % (airing_date_obj.strftime('%Y-%m-%d'), time)
                   
        if event['airings'][0]['is_live']:
            parameters = {
                'action': 'play_video',
                'channel_id': channel_id,
                'airing_id': airing_id
            }
            playable = True
            date_color = 'live'
        else:
            message = '%s [B]%s[/B].' % (language(30024), start_time)
            parameters = {
                'action': 'show_dialog',
                'dialog_type': 'ok',
                'heading': language(30025),
                'message': message
            }
            playable = False
            date_color = 'upcoming'
               
        info = {
            'title': event['title'],
            'plot': event['title'],
            'genre': sport_tag
        }
        
        try:
            event_images = event['urls']
            highest_res = 0
            for image in event_images:
                image_res = int(image['size'].split('_')[2])
                if image_res > highest_res:
                    art = {
                    'thumb': image['src'],
                    'fanart': image['src'],
                    'cover': image['src']
                    }
                    highest_res = image_res
        except KeyError:
            art = None
                   
        list_title = '[B]%s[/B] %s: %s' % (coloring(start_time, date_color), coloring(channel_name, 'channel'), event['title'])
        if event['airings'][0]['replay']:
            list_title = '%s [B]%s[/B]' % (list_title, coloring('(R)', 'replay'))

        items = add_item(list_title, parameters, items=items, playable=playable, set_art=art, set_info=info)
    xbmcplugin.addDirectoryItems(_handle, items, len(items))
    xbmcplugin.endOfDirectory(_handle)
    
def show_auth_details():
    auth_details = fs.refresh_session()['user']['registration']
    
    tv_provider = auth_details['auth_provider']
    entitlements = ', '.join(auth_details['entitlements'])
    expiration_date_obj = fs.parse_datetime(auth_details['expires_on'], localize=True)
    if addon.getSetting('time_notation') == '0':  # 12 hour clock
        expiration_date = expiration_date_obj.strftime('%Y-%m-%d %I:%M %p')
    else:
        expiration_date = expiration_date_obj.strftime('%Y-%m-%d %H:%M')
        
    tv_provider_msg = '[B]%s:[/B] %s' % (language(30031), tv_provider) 
    entitlements_msg = '[B]%s:[/B] %s' % (language(30032), entitlements) 
    expiration_date_msg = '%s [B]%s[/B].' % (language(30033), expiration_date)
    message = '%s[CR]%s[CR][CR]%s' % (tv_provider_msg, entitlements_msg, expiration_date_msg)
    log_out = show_dialog('yesno', language(30030), message, nolabel=language(30027), yeslabel=language(30034))

    if log_out:
        confirm_log_out = show_dialog('yesno', language(30034), language(30035))
        if confirm_log_out:
            fs.reset_credentials()
            sys.exit(0)

    
def list_event_dates():
    event_dates = fs.get_event_dates()
    now = datetime.now()
    date_today = now.date()
    
    for date in event_dates:
        # only list upcoming days
        if date > date_today:
            title = date.strftime('%Y-%m-%d')
            parameters = {
                'action': 'list_events_by_date',
                'schedule_type': 'all',
                'filter_date': date
            }
        
            add_item(title, parameters)
    xbmcplugin.endOfDirectory(_handle)


def ask_bitrate(bitrates):
    """Presents a dialog for user to select from a list of bitrates.
    Returns the value of the selected bitrate."""
    options = []
    for bitrate in bitrates:
        options.append(bitrate + ' Kbps')
    dialog = xbmcgui.Dialog()
    ret = dialog.select(language(30016), options)
    if ret > -1:
        return bitrates[ret]
    else:
        return None


def select_bitrate(manifest_bitrates=None):
    """Returns a bitrate while honoring the user's preference."""
    bitrate_setting = int(addon.getSetting('preferred_bitrate'))
    if bitrate_setting == 0:
        preferred_bitrate = 'highest'
    elif bitrate_setting == 1:
        preferred_bitrate = 'limit'
    else:
        preferred_bitrate = 'ask'

    manifest_bitrates.sort(key=int, reverse=True)
    if preferred_bitrate == 'highest':
        return manifest_bitrates[0]
    elif preferred_bitrate == 'limit':
        allowed_bitrates = []
        max_bitrate_allowed = int(addon.getSetting('max_bitrate_allowed'))
        for bitrate in manifest_bitrates:
            if max_bitrate_allowed >= int(bitrate):
                allowed_bitrates.append(str(bitrate))
        if allowed_bitrates:
            return allowed_bitrates[0]
    else:
        return ask_bitrate(manifest_bitrates)

        
def show_dialog(dialog_type, heading, message, nolabel=None, yeslabel=None):
    dialog = xbmcgui.Dialog()
    if dialog_type == 'ok':
        dialog.ok(heading, message)
    elif dialog_type == 'yesno':
        return dialog.yesno(heading, message, nolabel=nolabel, yeslabel=yeslabel)
        

def add_item(title, parameters, items=False, folder=True, playable=False, set_info=False, set_art=False,
             watched=False, set_content=False):
    listitem = xbmcgui.ListItem(label=title)
    if playable:
        listitem.setProperty('IsPlayable', 'true')
        folder = False
    if set_art:
        listitem.setArt(set_art)
    else:
        listitem.setArt({'icon': os.path.join(addon_path, 'icon.png')})
        listitem.setArt({'fanart': os.path.join(addon_path, 'fanart.jpg')})
    if set_info:
        listitem.setInfo('video', set_info)
    if not watched:
        listitem.addStreamInfo('video', {'duration': 0})
    if set_content:
        xbmcplugin.setContent(_handle, set_content)

    listitem.setContentLookup(False)  # allows sending custom headers/cookies to ffmpeg
    recursive_url = _url + '?' + urllib.urlencode(parameters)

    if items is False:
        xbmcplugin.addDirectoryItem(_handle, recursive_url, listitem, folder)
    else:
        items.append((recursive_url, listitem, folder))
        return items


def init(reg_code=None):
    try:
        fs.login(reg_code)
        main_menu()
    except fs.LoginFailure as error:
        if error.value == 'NoRegCode' or error.value == 'AuthRequired':
            reg_code = fs.get_reg_code()
            info_message = '%s[B]%s[/B] [CR][CR]%s' % (language(30010), reg_code, language(30011))
            ok = show_dialog('yesno', language(30009), info_message, nolabel=language(30028), yeslabel=language(30027))
            if ok:
                init(reg_code)
            else:
                sys.exit(0)
        elif error.value == 'AuthFailure':
            try_again = show_dialog('yesno', language(30012), language(30013), nolabel=language(30028), yeslabel=language(30029))
            if try_again:
                init()
            else:
                sys.exit(0)


def router(paramstring):
    """Router function that calls other functions depending on the provided paramstring."""
    params = dict(urlparse.parse_qsl(paramstring))
    if params:
        if params['action'] == 'play_video':
            play_video(params['channel_id'], params['airing_id'])
        elif params['action'] == 'list_events':
            list_events(params['schedule_type'])
        elif params['action'] == 'list_events_by_date':
            list_events(params['schedule_type'], params['filter_date'])
        elif params['action'] == 'list_event_dates':
            list_event_dates()
        elif params['action'] == 'show_auth_details':
            show_auth_details()
        elif params['action'] == 'show_dialog':
            show_dialog(params['dialog_type'], params['heading'], params['message'])
    else:
        init()


if __name__ == '__main__':
    router(sys.argv[2][1:])  # trim the leading '?' from the plugin call paramstring
