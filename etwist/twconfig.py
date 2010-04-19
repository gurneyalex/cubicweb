"""twisted server configurations:

* the "twisted" configuration to get a web instance running in a standalone
  twisted web server which talk to a repository server using Pyro

* the "all-in-one" configuration to get a web instance running in a twisted
  web server integrating a repository server in the same process (only available
  if the repository part of the software is installed

:organization: Logilab
:copyright: 2001-2010 LOGILAB S.A. (Paris, FRANCE), license is LGPL v2.
:contact: http://www.logilab.fr/ -- mailto:contact@logilab.fr
:license: GNU Lesser General Public License, v2.1 - http://www.gnu.org/licenses
"""
__docformat__ = "restructuredtext en"

from os.path import join

from logilab.common.configuration import Method

from cubicweb.web.webconfig import WebConfiguration, merge_options

class TwistedConfiguration(WebConfiguration):
    """web instance (in a twisted web server) client of a RQL server"""
    name = 'twisted'

    options = merge_options((
        # ctl configuration
        ('host',
         {'type' : 'string',
          'default': None,
          'help': 'host name if not correctly detectable through gethostname',
          'group': 'main', 'level': 1,
          }),
        ('port',
         {'type' : 'int',
          'default': None,
          'help': 'http server port number (default to 8080)',
          'group': 'main', 'level': 0,
          }),
        ('pid-file',
         {'type' : 'string',
          'default': Method('default_pid_file'),
          'help': 'repository\'s pid file',
          'group': 'main', 'level': 2,
          }),
        ('uid',
         {'type' : 'string',
          'default': None,
          'help': 'if this option is set, use the specified user to start \
the repository rather than the user running the command',
          'group': 'main', 'level': WebConfiguration.mode == 'system'
          }),
        ('max-post-length',
         {'type' : 'bytes',
          'default': '100MB',
          'help': 'maximum length of HTTP request. Default to 100 MB.',
          'group': 'main', 'level': 1,
          }),
        ('session-time',
         {'type' : 'time',
          'default': '30min',
          'help': 'session expiration time, default to 30 minutes',
          'group': 'main', 'level': 1,
          }),
        ('profile',
         {'type' : 'string',
          'default': None,
          'help': 'profile code and use the specified file to store stats if this option is set',
          'group': 'main', 'level': 2,
          }),
        ('pyro-server',
         {'type' : 'yn',
          # pyro is only a recommends by default, so don't activate it here
          'default': False,
          'help': 'run a pyro server',
          'group': 'main', 'level': 1,
          }),
        ) + WebConfiguration.options)

    def server_file(self):
        return join(self.apphome, '%s-%s.py' % (self.appid, self.name))

    def default_base_url(self):
        from socket import gethostname
        return 'http://%s:%s/' % (self['host'] or gethostname(), self['port'] or 8080)

try:
    from cubicweb.server.serverconfig import ServerConfiguration

    class AllInOneConfiguration(TwistedConfiguration, ServerConfiguration):
        """repository and web instance in the same twisted process"""
        name = 'all-in-one'
        repo_method = 'inmemory'
        options = merge_options(TwistedConfiguration.options
                                + ServerConfiguration.options)

        cubicweb_appobject_path = TwistedConfiguration.cubicweb_appobject_path | ServerConfiguration.cubicweb_appobject_path
        cube_appobject_path = TwistedConfiguration.cube_appobject_path | ServerConfiguration.cube_appobject_path
        def pyro_enabled(self):
            """tell if pyro is activated for the in memory repository"""
            return self['pyro-server']

except ImportError:
    pass
