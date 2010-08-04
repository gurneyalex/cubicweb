# copyright 2003-2010 LOGILAB S.A. (Paris, FRANCE), all rights reserved.
# contact http://www.logilab.fr/ -- mailto:contact@logilab.fr
#
# This file is part of CubicWeb.
#
# CubicWeb is free software: you can redistribute it and/or modify it under the
# terms of the GNU Lesser General Public License as published by the Free
# Software Foundation, either version 2.1 of the License, or (at your option)
# any later version.
#
# CubicWeb is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with CubicWeb.  If not, see <http://www.gnu.org/licenses/>.
"""web ui configuration for cubicweb instances"""

__docformat__ = "restructuredtext en"
_ = unicode

import os
from os.path import join, exists, split
from warnings import warn

from logilab.common.decorators import cached
from logilab.common.deprecation import deprecated

from cubicweb.toolsutils import read_config
from cubicweb.cwconfig import CubicWebConfiguration, register_persistent_options, merge_options


register_persistent_options( (
    # site-wide only web ui configuration
    ('site-title',
     {'type' : 'string', 'default': 'unset title',
      'help': _('site title'),
      'sitewide': True, 'group': 'ui',
      }),
    ('main-template',
     {'type' : 'string', 'default': 'main-template',
      'help': _('id of main template used to render pages'),
      'sitewide': True, 'group': 'ui',
      }),
    # user web ui configuration
    ('fckeditor',
     {'type' : 'yn', 'default': True,
      'help': _('should html fields being edited using fckeditor (a HTML '
                'WYSIWYG editor).  You should also select text/html as default '
                'text format to actually get fckeditor.'),
      'group': 'ui',
      }),
    # navigation configuration
    ('page-size',
     {'type' : 'int', 'default': 40,
      'help': _('maximum number of objects displayed by page of results'),
      'group': 'navigation',
      }),
    ('related-limit',
     {'type' : 'int', 'default': 8,
      'help': _('maximum number of related entities to display in the primary '
                'view'),
      'group': 'navigation',
      }),
    ('combobox-limit',
     {'type' : 'int', 'default': 20,
      'help': _('maximum number of entities to display in related combo box'),
      'group': 'navigation',
      }),

    ))


class WebConfiguration(CubicWebConfiguration):
    """the WebConfiguration is a singleton object handling instance's
    configuration and preferences
    """
    cubicweb_appobject_path = CubicWebConfiguration.cubicweb_appobject_path | set([join('web', 'views')])
    cube_appobject_path = CubicWebConfiguration.cube_appobject_path | set(['views'])
    uiprops = {'FCKEDITOR_PATH': ''}

    options = merge_options(CubicWebConfiguration.options + (
        ('anonymous-user',
         {'type' : 'string',
          'default': None,
          'help': 'login of the CubicWeb user account to use for anonymous user (if you want to allow anonymous)',
          'group': 'web', 'level': 1,
          }),
        ('anonymous-password',
         {'type' : 'string',
          'default': None,
          'help': 'password of the CubicWeb user account to use for anonymous user, '
          'if anonymous-user is set',
          'group': 'web', 'level': 1,
          }),
        ('query-log-file',
         {'type' : 'string',
          'default': None,
          'help': 'web instance query log file',
          'group': 'web', 'level': 3,
          }),
        # web configuration
        ('https-url',
         {'type' : 'string',
          'default': None,
          'help': 'web server root url on https. By specifying this option your '\
          'site can be available as an http and https site. Authenticated users '\
          'will in this case be authenticated and once done navigate through the '\
          'https site. IMPORTANTE NOTE: to do this work, you should have your '\
          'apache redirection include "https" as base url path so cubicweb can '\
          'differentiate between http vs https access. For instance: \n'\
          'RewriteRule ^/demo/(.*) http://127.0.0.1:8080/https/$1 [L,P]\n'\
          'where the cubicweb web server is listening on port 8080.',
          'group': 'main', 'level': 3,
          }),
        ('auth-mode',
         {'type' : 'choice',
          'choices' : ('cookie', 'http'),
          'default': 'cookie',
          'help': 'authentication mode (cookie / http)',
          'group': 'web', 'level': 3,
          }),
        ('realm',
         {'type' : 'string',
          'default': 'cubicweb',
          'help': 'realm to use on HTTP authentication mode',
          'group': 'web', 'level': 3,
          }),
        ('http-session-time',
         {'type' : 'time',
          'default': 0,
          'help': "duration of the cookie used to store session identifier. "
          "If 0, the cookie will expire when the user exist its browser. "
          "Should be 0 or greater than repository\'s session-time.",
          'group': 'web', 'level': 2,
          }),
        ('cleanup-session-time',
         {'type' : 'time',
          'default': '24h',
          'help': 'duration of inactivity after which a connection '
          'will be closed, to limit memory consumption (avoid sessions that '
          'never expire and cause memory leak when http-session-time is 0). '
          'So even if http-session-time is 0 and the user don\'t close his '
          'browser, he will have to reauthenticate after this time of '
          'inactivity. Default to 24h.',
          'group': 'web', 'level': 3,
          }),
        ('cleanup-anonymous-session-time',
         {'type' : 'time',
          'default': '5min',
          'help': 'Same as cleanup-session-time but specific to anonymous '
          'sessions. You can have a much smaller timeout here since it will be '
          'transparent to the user. Default to 5min.',
          'group': 'web', 'level': 3,
          }),
        ('force-html-content-type',
         {'type' : 'yn',
          'default': False,
          'help': 'force text/html content type for your html pages instead of cubicweb user-agent based'\
          'deduction of an appropriate content type',
          'group': 'web', 'level': 3,
          }),
        ('embed-allowed',
         {'type' : 'regexp',
          'default': None,
          'help': 'regular expression matching URLs that may be embeded. \
leave it blank if you don\'t want the embedding feature, or set it to ".*" \
if you want to allow everything',
          'group': 'web', 'level': 3,
          }),
        ('submit-mail',
         {'type' : 'string',
          'default': None,
          'help': ('Mail used as recipient to report bug in this instance, '
                   'if you want this feature on'),
          'group': 'web', 'level': 2,
          }),

        ('language-negociation',
         {'type' : 'yn',
          'default': True,
          'help': 'use Accept-Language http header to try to set user '\
          'interface\'s language according to browser defined preferences',
          'group': 'web', 'level': 2,
          }),

        ('print-traceback',
         {'type' : 'yn',
          'default': CubicWebConfiguration.mode != 'system',
          'help': 'print the traceback on the error page when an error occured',
          'group': 'web', 'level': 2,
          }),

        ('captcha-font-file',
         {'type' : 'string',
          'default': join(CubicWebConfiguration.shared_dir(), 'data', 'porkys.ttf'),
          'help': 'True type font to use for captcha image generation (you \
must have the python imaging library installed to use captcha)',
          'group': 'web', 'level': 3,
          }),
        ('captcha-font-size',
         {'type' : 'int',
          'default': 25,
          'help': 'Font size to use for captcha image generation (you must \
have the python imaging library installed to use captcha)',
          'group': 'web', 'level': 3,
          }),

        ('use-old-css',
         {'type' : 'yn',
          'default': True,
          'help': 'use cubicweb.old.css instead of 3.9 cubicweb.css',
          'group': 'web', 'level': 2,
          }),


        ))

    def fckeditor_installed(self):
        return exists(self.uiprops['FCKEDITOR_PATH'])

    def eproperty_definitions(self):
        for key, pdef in super(WebConfiguration, self).eproperty_definitions():
            if key == 'ui.fckeditor' and not self.fckeditor_installed():
                continue
            yield key, pdef

    # method used to connect to the repository: 'inmemory' / 'pyro'
    # Pyro repository by default
    repo_method = 'pyro'

    # don't use @cached: we want to be able to disable it while this must still
    # be cached
    def repository(self, vreg=None):
        """return the instance's repository object"""
        try:
            return self.__repo
        except AttributeError:
            from cubicweb.dbapi import get_repository
            repo = get_repository(self.repo_method, vreg=vreg, config=self)
            self.__repo = repo
            return repo

    def vc_config(self):
        return self.repository().get_versions()

    def anonymous_user(self):
        """return a login and password to use for anonymous users. None
        may be returned for both if anonymous connections are not allowed
        """
        try:
            user = self['anonymous-user']
            passwd = self['anonymous-password']
        except KeyError:
            user, passwd = None, None
        if user is not None:
            user = unicode(user)
        return user, passwd

    def locate_resource(self, rid):
        """return the (directory, filename) where the given resource
        may be found
        """
        return self._fs_locate(rid, 'data')

    def locate_doc_file(self, fname):
        """return the directory where the given resource may be found"""
        return self._fs_locate(fname, 'wdoc')[0]

    @cached
    def _fs_path_locate(self, rid, rdirectory):
        """return the directory where the given resource may be found"""
        path = [self.apphome] + self.cubes_path() + [join(self.shared_dir())]
        for directory in path:
            if exists(join(directory, rdirectory, rid)):
                return directory

    def _fs_locate(self, rid, rdirectory):
        """return the (directory, filename) where the given resource
        may be found
        """
        directory = self._fs_path_locate(rid, rdirectory)
        if directory is None:
            return None, None
        if rdirectory == 'data' and rid.endswith('.css'):
            if self['use-old-css'] and rid == 'cubicweb.css':
                # @import('cubicweb.css') in css
                rid = 'cubicweb.old.css'
            return self.uiprops.process_resource(join(directory, rdirectory), rid), rid
        return join(directory, rdirectory), rid

    def locate_all_files(self, rid, rdirectory='wdoc'):
        """return all files corresponding to the given resource"""
        path = [self.apphome] + self.cubes_path() + [join(self.shared_dir())]
        for directory in path:
            fpath = join(directory, rdirectory, rid)
            if exists(fpath):
                yield join(fpath)

    def load_configuration(self):
        """load instance's configuration files"""
        super(WebConfiguration, self).load_configuration()
        # load external resources definition
        self._init_base_url()
        self._build_ui_properties()

    def _init_base_url(self):
        # normalize base url(s)
        baseurl = self['base-url'] or self.default_base_url()
        if baseurl and baseurl[-1] != '/':
            baseurl += '/'
        if not self.repairing:
            self.global_set_option('base-url', baseurl)
        httpsurl = self['https-url']
        if httpsurl:
            if httpsurl[-1] != '/':
                httpsurl += '/'
                if not self.repairing:
                    self.global_set_option('https-url', httpsurl)
            if self.debugmode:
                self.https_datadir_url = httpsurl + 'data/'
            else:
                self.https_datadir_url = httpsurl + 'data%s/' % self.instance_md5_version()
        if self.debugmode:
            self.datadir_url = baseurl + 'data/'
        else:
            self.datadir_url = baseurl + 'data%s/' % self.instance_md5_version()

    def _build_ui_properties(self):
        # self.datadir_url[:-1] to remove trailing /
        from cubicweb.web.propertysheet import PropertySheet
        cachedir = join(self.appdatahome, 'uicache')
        self.check_writeable_uid_directory(cachedir)
        self.uiprops = PropertySheet(
            cachedir,
            data=lambda x: self.datadir_url + x,
            datadir_url=self.datadir_url[:-1])
        self._init_uiprops(self.uiprops)
        if self['https-url']:
            cachedir = join(self.appdatahome, 'uicachehttps')
            self.check_writeable_uid_directory(cachedir)
            self.https_uiprops = PropertySheet(
                cachedir,
                data=lambda x: self.https_datadir_url + x,
                datadir_url=self.https_datadir_url[:-1])
            self._init_uiprops(self.https_uiprops)

    def _init_uiprops(self, uiprops):
        libuiprops = join(self.shared_dir(), 'data', 'uiprops.py')
        uiprops.load(libuiprops)
        for path in reversed([self.apphome] + self.cubes_path()):
            self._load_ui_properties_file(uiprops, path)
        self._load_ui_properties_file(uiprops, self.apphome)
        datadir_url = uiprops.context['datadir_url']
        # XXX pre 3.9 css compat
        if self['use-old-css']:
            if (datadir_url+'/cubicweb.css') in uiprops['STYLESHEETS']:
                idx = uiprops['STYLESHEETS'].index(datadir_url+'/cubicweb.css')
                uiprops['STYLESHEETS'][idx] = datadir_url+'/cubicweb.old.css'
            if datadir_url+'/cubicweb.reset.css' in uiprops['STYLESHEETS']:
                uiprops['STYLESHEETS'].remove(datadir_url+'/cubicweb.reset.css')
        cubicweb_js_url = datadir_url + '/cubicweb.js'
        if cubicweb_js_url not in uiprops['JAVASCRIPTS']:
            uiprops['JAVASCRIPTS'].insert(0, cubicweb_js_url)

    def _load_ui_properties_file(self, uiprops, path):
        resourcesfile = join(path, 'data', 'external_resources')
        if exists(resourcesfile):
            warn('[3.9] %s file is deprecated, use an uiprops.py file'
                 % resourcesfile, DeprecationWarning)
            datadir_url = uiprops.context['datadir_url']
            for rid, val in read_config(resourcesfile).iteritems():
                if rid in ('STYLESHEETS', 'STYLESHEETS_PRINT',
                           'IE_STYLESHEETS', 'JAVASCRIPTS'):
                    val = [w.strip().replace('DATADIR', datadir_url)
                           for w in val.split(',') if w.strip()]
                    if rid == 'IE_STYLESHEETS':
                        rid = 'STYLESHEETS_IE'
                else:
                    val = val.strip().replace('DATADIR', datadir_url)
                uiprops[rid] = val
        uipropsfile = join(path, 'uiprops.py')
        if exists(uipropsfile):
            self.debug('loading %s', uipropsfile)
            uiprops.load(uipropsfile)

    # static files handling ###################################################

    @property
    def static_directory(self):
        return join(self.appdatahome, 'static')

    def static_file_exists(self, rpath):
        return exists(join(self.static_directory, rpath))

    def static_file_open(self, rpath, mode='wb'):
        staticdir = self.static_directory
        rdir, filename = split(rpath)
        if rdir:
            staticdir = join(staticdir, rdir)
            os.makedirs(staticdir)
        return file(join(staticdir, filename), mode)

    def static_file_add(self, rpath, data):
        stream = self.static_file_open(rpath)
        stream.write(data)
        stream.close()

    def static_file_del(self, rpath):
        if self.static_file_exists(rpath):
            os.remove(join(self.static_directory, rpath))

    @deprecated('[3.9] use _cw.uiprops.get(rid)')
    def has_resource(self, rid):
        """return true if an external resource is defined"""
        return bool(self.uiprops.get(rid))
