# -*- coding: utf-8 -*-
"""
A Kodi-agnostic library for FOX Sports GO
"""
import json
import codecs
import cookielib
import time
from urllib import urlencode
import uuid

import requests
import m3u8


class fslib(object):
    def __init__(self, cookie_file, credentials_file, debug=False, verify_ssl=True):
        self.debug = debug
        self.verify_ssl = verify_ssl
        self.http_session = requests.Session()
        self.cookie_jar = cookielib.LWPCookieJar(cookie_file)
        self.credentials_file = credentials_file
        self.base_url = 'https://media-api.foxsportsgo.com'
        try:
            self.cookie_jar.load(ignore_discard=True, ignore_expires=True)
        except IOError:
            pass
        self.http_session.cookies = self.cookie_jar
        try:
            with open(self.credentials_file, 'r') as fh_credentials:
                credentials = json.loads(fh_credentials.read())
                self.session_id = credentials['session_id']
                self.auth_header = credentials['auth_header']
        except IOError:
            self.session_id = None
            self.auth_header = None

    class LoginFailure(Exception):
        def __init__(self, value):
            self.value = value

        def __str__(self):
            return repr(self.value)

    def log(self, string):
        if self.debug:
            try:
                print '[fsgolib]: %s' % string
            except UnicodeEncodeError:
                # we can't anticipate everything in unicode they might throw at
                # us, but we can handle a simple BOM
                bom = unicode(codecs.BOM_UTF8, 'utf8')
                print '[fsgolib]: %s' % string.replace(bom, '')
            except:
                pass

    def make_request(self, url, method, payload=None, headers=None, return_req=False):
        """Make an HTTP request. Return the response."""
        self.log('Request URL: %s' % url)
        try:
            if method == 'get':
                req = self.http_session.get(url, params=payload, headers=headers, allow_redirects=False,
                                            verify=self.verify_ssl)
            elif method == 'put':
                req = self.http_session.put(url, params=payload, headers=headers, allow_redirects=False,
                                            verify=self.verify_ssl)
            else:  # post
                req = self.http_session.post(url, data=payload, headers=headers, allow_redirects=False,
                                             verify=self.verify_ssl)
            self.log('Response code: %s' % req.status_code)
            self.log('Response: %s' % req.content)
            self.cookie_jar.save(ignore_discard=True, ignore_expires=False)
            if return_req:
                return req
            else:
                return req.content
        except requests.exceptions.ConnectionError as error:
            self.log('Connection Error: - %s' % error.message)
            raise
        except requests.exceptions.RequestException as error:
            self.log('Error: - %s' % error.value)
            raise

    def get_reg_code(self):
        url = 'https://activation-adobe.foxsportsgo.com/ws/subscription/flow/foxSportGo.init'
        payload = {
            'env': 'production',
            'request_type': 'new_session',
            'requestor_id': 'fs2go',
            '_': str(time.time())  # unix timestamp
        }
        code_data = self.make_request(url=url, method='get', payload=payload)
        code_dict = json.loads(code_data)

        return code_dict['code']

    def get_access_token(self, reg_code):
        url = 'https://activation-adobe.foxsportsgo.com/ws/subscription/flow/v2_foxSportsGo.validate'
        payload = {
            'reg_code': reg_code,
            'env': 'production',
            'request_type': 'validate_session',
            'requestor_id': 'fs2go',
            'device_id': str(uuid.uuid4()),
            'platform': 'Device',
            '_': str(time.time())  # unix timestamp
        }
        reg_data = self.make_request(url=url, method='get', payload=payload)
        reg_dict = json.loads(reg_data)

        if reg_dict['status'] == 'Success':
            self.log('Successfully authenticated to TV provider (%s)' % reg_dict['auth_provider_name'])
            return reg_dict['access_token']
        else:
            self.log('Unable to authenticate to TV provider. Status: %s' % reg_dict['status'])
            return False

    def register_session(self, access_token):
        url = self.base_url + '/sessions/registered'
        session = {}
        auth = {}
        session['device'] = {}
        session['location'] = {}
        session['device']['token'] = access_token
        session['device']['platform'] = 'ios-tablet'
        session['location']['latitude'] = '0'
        session['location']['longitude'] = '0'
        post_data = json.JSONEncoder().encode(session)

        headers = {
            'Accept': 'application/vnd.session-service+json; version=1',
            'Content-Type': 'application/vnd.session-service+json; version=1'
        }

        req = self.make_request(url=url, method='post', payload=post_data, headers=headers, return_req=True)
        session_dict = json.loads(req.content)
        if 'errors' in session_dict.keys():
            errors = []
            for error in session_dict.values():
                errors.append(error)
            self.log('Unable to register session. Error(s): %s' % errors)
            return False
        else:
            auth_header = req.headers['Authorization']
            auth['session_id'] = session_dict['id']
            auth['auth_header'] = auth_header
            with open(self.credentials_file, 'w') as fh_credentials:
                fh_credentials.write(json.JSONEncoder().encode(auth))
            self.log('Successfully registered session.')
            return True

    def refresh_session(self):
        url = self.base_url + '/sessions/%s/refresh' % self.session_id
        auth = {}
        headers = {
            'Accept': 'application/vnd.session-service+json; version=1',
            'Content-Type': 'application/vnd.session-service+json; version=1',
            'Authorization': self.auth_header
        }
        req = self.make_request(url=url, method='put', headers=headers, return_req=True)
        session_data = req.content
        try:
            session_dict = json.loads(session_data)
        except ValueError:
            session_dict = None

        if session_dict:
            if 'errors' in session_dict.keys():
                errors = []
                for error in session_dict.values():
                    errors.append(error)
                self.log('Unable to refresh session. Error(s): %s' % errors)
                return False
            else:
                auth_header = req.headers['Authorization']
                auth['session_id'] = session_dict['id']
                auth['auth_header'] = auth_header
                with open(self.credentials_file, 'w') as fh_credentials:
                    fh_credentials.write(json.JSONEncoder().encode(auth))
                return True
        else:
            return False

    def login(self, reg_code=None, session_id=None, auth_header=None):
        if session_id and auth_header:
            if self.refresh_session():
                self.log('Session is still valid.')
                return True
            else:
                self.log('No valid session found. Authorization needed.')
                raise self.LoginFailure('No valid session found. Authorization needed.')
        else:
            if reg_code:
                self.log('Not (yet) logged in.')
                access_token = self.get_access_token(reg_code)
                if not access_token:
                    raise self.LoginFailure('Authorization failure.')
                else:
                    if not self.register_session(access_token):
                        raise self.LoginFailure('Unable to register session.')
                    else:
                        self.log('Login was successful.')
                        return True
            else:
                self.log('No registration code supplied.')
                raise self.LoginFailure('No registration code supplied.')

    def get_stream_url(self, channel_id):
        stream_url = {}
        url = self.base_url + '/platform/web/channel/%s' % channel_id
        headers = {
            'Accept': 'application/vnd.media-service+json; version=1',
            'Authorization': self.auth_header
        }
        stream_data = self.make_request(url=url, method='get', headers=headers)
        stream_dict = json.loads(stream_data)['stream']
        stream_url['manifest'] = stream_dict['location']
        stream_url['bitrates'] = self.parse_m3u8_manifest(stream_url['manifest'])

        return stream_url

    def parse_m3u8_manifest(self, manifest_url):
        """Return the stream URL along with its bitrate."""
        streams = {}
        req = requests.get(manifest_url)
        m3u8_manifest = req.content
        self.log('HLS manifest: \n %s' % m3u8_manifest)

        m3u8_header = {'Cookie': 'Authorization=' + self.auth_header}
        m3u8_obj = m3u8.loads(m3u8_manifest)
        for playlist in m3u8_obj.playlists:
            bitrate = int(playlist.stream_info.bandwidth) / 1000
            if playlist.uri.startswith('http'):
                stream_url = playlist.uri
            else:
                stream_url = manifest_url[:manifest_url.rfind('/') + 1] + playlist.uri
            streams[str(bitrate)] = stream_url + '|' + urlencode(m3u8_header)

        return streams

    def get_schedule(start_date, end_date):
        url = self.base_url + '/epg/ws/schedule'
        payload = {
            'start_date': start_date,
            'end_date': end_date
        }
        schedule_data = self.make_request(url=url, method='get', payload=payload)
        schedule_dict = json.loads(schedule_data)
        schedule = schedule_dict['body']['items']

        return schedule
