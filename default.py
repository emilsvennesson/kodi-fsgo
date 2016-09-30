# -*- coding: utf-8 -*-
"""
A Kodi plugin for ESPN Player
"""
import sys
import os
import urllib
import urlparse

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


def play_video(channel_id):
    stream_url = fs.get_stream_url(channel_id)
    if stream_url['bitrates']:
        bitrate = select_bitrate(stream_url['bitrates'].keys())
        if bitrate:
            play_url = stream_url['bitrates'][bitrate]
            playitem = xbmcgui.ListItem(path=play_url)
            playitem.setProperty('IsPlayable', 'true')
            xbmcplugin.setResolvedUrl(_handle, True, listitem=playitem)
    else:
        dialog = xbmcgui.Dialog()
        dialog.ok(language(30005), language(30013))


def ask_bitrate(bitrates):
    """Presents a dialog for user to select from a list of bitrates.
    Returns the value of the selected bitrate."""
    options = []
    for bitrate in bitrates:
        options.append(bitrate + ' Kbps')
    dialog = xbmcgui.Dialog()
    ret = dialog.select(language(30010), options)
    if ret > -1:
        return bitrates[ret]


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


def authenticate(reg_code=None, session_id=None, auth_header=None):
    try:
        fs.login(session_id=session_id, auth_header=auth_header, reg_code=reg_code)
    except fs.LoginFailure as error:
        if error.value == 'No registration code supplied.' or error.value == 'No valid session found. Authorization needed.':
            reg_code = fs.get_reg_code()
            dialog = xbmcgui.Dialog()
            info_message = '%s[B]%s[/B] [CR][CR]%s' % (language(30010), reg_code, language(30011))
            dialog.ok(language(30009), info_message)
            authenticate(reg_code)
        elif error.value == 'Authorization failure.':
            dialog = xbmcgui.Dialog()
            dialog.ok(language(30012), language(30013))


def router(paramstring):
    """Router function that calls other functions depending on the provided paramstring."""
    params = dict(urlparse.parse_qsl(paramstring))
    if params:
        if params['action'] == 'play_video':
            play_video(params['channel_id'])
    else:
        authenticate(session_id=fs.session_id, auth_header=fs.auth_header)


if __name__ == '__main__':
    router(sys.argv[2][1:])  # trim the leading '?' from the plugin call paramstring
