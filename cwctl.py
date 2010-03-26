"""the cubicweb-ctl tool, based on logilab.common.clcommands to
provide a pluggable commands system.


:organization: Logilab
:copyright: 2001-2010 LOGILAB S.A. (Paris, FRANCE), license is LGPL v2.
:contact: http://www.logilab.fr/ -- mailto:contact@logilab.fr
:license: GNU Lesser General Public License, v2.1 - http://www.gnu.org/licenses
"""
__docformat__ = "restructuredtext en"

# *ctl module should limit the number of import to be imported as quickly as
# possible (for cubicweb-ctl reactivity, necessary for instance for usable bash
# completion). So import locally in command helpers.
import sys
from os import remove, listdir, system, pathsep
try:
    from os import kill, getpgid
except ImportError:
    def kill(*args):
        """win32 kill implementation"""
    def getpgid():
        """win32 getpgid implementation"""

from os.path import exists, join, isfile, isdir, dirname, abspath

from logilab.common.clcommands import register_commands, pop_arg
from logilab.common.shellutils import ASK

from cubicweb import ConfigurationError, ExecutionError, BadCommandUsage
from cubicweb.cwconfig import CubicWebConfiguration as cwcfg, CWDEV, CONFIGURATIONS
from cubicweb.toolsutils import Command, main_run, rm, create_dir, underline_title

def wait_process_end(pid, maxtry=10, waittime=1):
    """wait for a process to actually die"""
    import signal
    from time import sleep
    nbtry = 0
    while nbtry < maxtry:
        try:
            kill(pid, signal.SIGUSR1)
        except (OSError, AttributeError): # XXX win32
            break
        nbtry += 1
        sleep(waittime)
    else:
        raise ExecutionError('can\'t kill process %s' % pid)

def list_instances(regdir):
    return sorted(idir for idir in listdir(regdir) if isdir(join(regdir, idir)))

def detect_available_modes(templdir):
    modes = []
    for fname in ('schema', 'schema.py'):
        if exists(join(templdir, fname)):
            modes.append('repository')
            break
    for fname in ('data', 'views', 'views.py'):
        if exists(join(templdir, fname)):
            modes.append('web ui')
            break
    return modes


class InstanceCommand(Command):
    """base class for command taking 0 to n instance id as arguments
    (0 meaning all registered instances)
    """
    arguments = '[<instance>...]'
    options = (
        ("force",
         {'short': 'f', 'action' : 'store_true',
          'default': False,
          'help': 'force command without asking confirmation',
          }
         ),
        )
    actionverb = None

    def ordered_instances(self):
        """return instances in the order in which they should be started,
        considering $REGISTRY_DIR/startorder file if it exists (useful when
        some instances depends on another as external source).

        Instance used by another one should appears first in the file (one
        instance per line)
        """
        regdir = cwcfg.registry_dir()
        _allinstances = list_instances(regdir)
        if isfile(join(regdir, 'startorder')):
            allinstances = []
            for line in file(join(regdir, 'startorder')):
                line = line.strip()
                if line and not line.startswith('#'):
                    try:
                        _allinstances.remove(line)
                        allinstances.append(line)
                    except ValueError:
                        print ('ERROR: startorder file contains unexistant '
                               'instance %s' % line)
            allinstances += _allinstances
        else:
            allinstances = _allinstances
        return allinstances

    def run(self, args):
        """run the <command>_method on each argument (a list of instance
        identifiers)
        """
        if not args:
            args = self.ordered_instances()
            try:
                askconfirm = not self.config.force
            except AttributeError:
                # no force option
                askconfirm = False
        else:
            askconfirm = False
        self.run_args(args, askconfirm)

    def run_args(self, args, askconfirm):
        for appid in args:
            if askconfirm:
                print '*'*72
                if not ASK.confirm('%s instance %r ?' % (self.name, appid)):
                    continue
            self.run_arg(appid)

    def run_arg(self, appid):
        cmdmeth = getattr(self, '%s_instance' % self.name)
        try:
            cmdmeth(appid)
        except (KeyboardInterrupt, SystemExit):
            print >> sys.stderr, '%s aborted' % self.name
            sys.exit(2) # specific error code
        except (ExecutionError, ConfigurationError), ex:
            print >> sys.stderr, 'instance %s not %s: %s' % (
                appid, self.actionverb, ex)
        except Exception, ex:
            import traceback
            traceback.print_exc()
            print >> sys.stderr, 'instance %s not %s: %s' % (
                appid, self.actionverb, ex)


class InstanceCommandFork(InstanceCommand):
    """Same as `InstanceCommand`, but command is forked in a new environment
    for each argument
    """

    def run_args(self, args, askconfirm):
        if len(args) > 1:
            forkcmd = ' '.join(w for w in sys.argv if not w in args)
        else:
            forkcmd = None
        for appid in args:
            if askconfirm:
                print '*'*72
                if not ASK.confirm('%s instance %r ?' % (self.name, appid)):
                    continue
            if forkcmd:
                status = system('%s %s' % (forkcmd, appid))
                if status:
                    print '%s exited with status %s' % (forkcmd, status)
            else:
                self.run_arg(appid)


# base commands ###############################################################

def version_strictly_lower(a, b):
    from logilab.common.changelog import Version
    if a:
        a = Version(a)
    if b:
        b = Version(b)
    return a < b

def max_version(a, b):
    from logilab.common.changelog import Version
    return str(max(Version(a), Version(b)))

class ConfigurationProblem(object):
    """Each cube has its own list of dependencies on other cubes/versions.

    The ConfigurationProblem is used to record the loaded cubes, then to detect
    inconsistencies in their dependencies.

    See configuration management on wikipedia for litterature.
    """

    def __init__(self):
        self.cubes = {}

    def add_cube(self, name, info):
        self.cubes[name] = info

    def solve(self):
        self.warnings = []
        self.errors = []
        self.read_constraints()
        for cube, versions in sorted(self.constraints.items()):
            oper, version = None, None
            # simplify constraints
            if versions:
                for constraint in versions:
                    op, ver = constraint
                    if oper is None:
                        oper = op
                        version = ver
                    elif op == '>=' and oper == '>=':
                        version = max_version(ver, version)
                    else:
                        print 'unable to handle this case', oper, version, op, ver
            # "solve" constraint satisfaction problem
            if cube not in self.cubes:
                self.errors.append( ('add', cube, version) )
            elif versions:
                lower_strict = version_strictly_lower(self.cubes[cube].version, version)
                if oper in ('>=','='):
                    if lower_strict:
                        self.errors.append( ('update', cube, version) )
                else:
                    print 'unknown operator', oper

    def read_constraints(self):
        self.constraints = {}
        self.reverse_constraints = {}
        for cube, info in self.cubes.items():
            if hasattr(info,'__depends_cubes__'):
                use = info.__depends_cubes__
                if not isinstance(use, dict):
                    use = dict((key, None) for key in use)
                    self.warnings.append('cube %s should define __depends_cubes__ as a dict not a list')
            else:
                self.warnings.append('cube %s should define __depends_cubes__' % cube)
                use = dict((key, None) for key in info.__use__)
            for name, constraint in use.items():
                self.constraints.setdefault(name,set())
                if constraint:
                    try:
                        oper, version = constraint.split()
                        self.constraints[name].add( (oper, version) )
                    except:
                        self.warnings.append('cube %s depends on %s but constraint badly formatted: %s'
                                             % (cube, name, constraint))
                self.reverse_constraints.setdefault(name, set()).add(cube)

class ListCommand(Command):
    """List configurations, cubes and instances.

    list available configurations, installed cubes, and registered instances
    """
    name = 'list'
    options = (
        ('verbose',
         {'short': 'v', 'action' : 'store_true',
          'help': "display more information."}),
        )

    def run(self, args):
        """run the command with its specific arguments"""
        if args:
            raise BadCommandUsage('Too much arguments')
        print 'CubicWeb %s (%s mode)' % (cwcfg.cubicweb_version(), cwcfg.mode)
        print
        print 'Available configurations:'
        for config in CONFIGURATIONS:
            print '*', config.name
            for line in config.__doc__.splitlines():
                line = line.strip()
                if not line:
                    continue
                print '   ', line
        print
        cfgpb = ConfigurationProblem()
        try:
            cubesdir = pathsep.join(cwcfg.cubes_search_path())
            namesize = max(len(x) for x in cwcfg.available_cubes())
        except ConfigurationError, ex:
            print 'No cubes available:', ex
        except ValueError:
            print 'No cubes available in %s' % cubesdir
        else:
            print 'Available cubes (%s):' % cubesdir
            for cube in cwcfg.available_cubes():
                if cube in ('CVS', '.svn', 'shared', '.hg'):
                    continue
                try:
                    tinfo = cwcfg.cube_pkginfo(cube)
                    tversion = tinfo.version
                    cfgpb.add_cube(cube, tinfo)
                except ConfigurationError:
                    tinfo = None
                    tversion = '[missing cube information]'
                print '* %s %s' % (cube.ljust(namesize), tversion)
                if self.config.verbose:
                    shortdesc = tinfo and (getattr(tinfo, 'short_desc', '')
                                           or tinfo.__doc__)
                    if shortdesc:
                        print '    '+ '    \n'.join(shortdesc.splitlines())
                    modes = detect_available_modes(cwcfg.cube_dir(cube))
                    print '    available modes: %s' % ', '.join(modes)
        print
        try:
            regdir = cwcfg.registry_dir()
        except ConfigurationError, ex:
            print 'No instance available:', ex
            print
            return
        instances = list_instances(regdir)
        if instances:
            print 'Available instances (%s):' % regdir
            for appid in instances:
                modes = cwcfg.possible_configurations(appid)
                if not modes:
                    print '* %s (BROKEN instance, no configuration found)' % appid
                    continue
                print '* %s (%s)' % (appid, ', '.join(modes))
                try:
                    config = cwcfg.config_for(appid, modes[0])
                except Exception, exc:
                    print '    (BROKEN instance, %s)' % exc
                    continue
        else:
            print 'No instance available in %s' % regdir
        print
        # configuration management problem solving
        cfgpb.solve()
        if cfgpb.warnings:
            print 'Warnings:\n', '\n'.join('* '+txt for txt in cfgpb.warnings)
        if cfgpb.errors:
            print 'Errors:'
            for op, cube, version in cfgpb.errors:
                if op == 'add':
                    print '* cube', cube,
                    if version:
                        print ' version', version,
                    print 'is not installed, but required by %s' % ' '.join(cfgpb.reverse_constraints[cube])
                else:
                    print '* cube %s version %s is installed, but version %s is required by (%s)' % (
                        cube, cfgpb.cubes[cube].version, version, ', '.join(cfgpb.reverse_constraints[cube]))

class CreateInstanceCommand(Command):
    """Create an instance from a cube. This is an unified
    command which can handle web / server / all-in-one installation
    according to available parts of the software library and of the
    desired cube.

    <cube>
      the name of cube to use (list available cube names using
      the "list" command). You can use several cubes by separating
      them using comma (e.g. 'jpl,eemail')
    <instance>
      an identifier for the instance to create
    """
    name = 'create'
    arguments = '<cube> <instance>'
    options = (
        ("config-level",
         {'short': 'l', 'type' : 'int', 'metavar': '<level>',
          'default': 0,
          'help': 'configuration level (0..2): 0 will ask for essential \
configuration parameters only while 2 will ask for all parameters',
          }
         ),
        ("config",
         {'short': 'c', 'type' : 'choice', 'metavar': '<install type>',
          'choices': ('all-in-one', 'repository', 'twisted'),
          'default': 'all-in-one',
          'help': 'installation type, telling which part of an instance \
should be installed. You can list available configurations using the "list" \
command. Default to "all-in-one", e.g. an installation embedding both the RQL \
repository and the web server.',
          }
         ),
        )

    def run(self, args):
        """run the command with its specific arguments"""
        from logilab.common.textutils import splitstrip
        configname = self.config.config
        cubes = splitstrip(pop_arg(args, 1))
        appid = pop_arg(args)
        # get the configuration and helper
        cwcfg.creating = True
        config = cwcfg.config_for(appid, configname)
        config.set_language = False
        cubes = config.expand_cubes(cubes)
        config.init_cubes(cubes)
        helper = self.config_helper(config)
        # check the cube exists
        try:
            templdirs = [cwcfg.cube_dir(cube)
                         for cube in cubes]
        except ConfigurationError, ex:
            print ex
            print '\navailable cubes:',
            print ', '.join(cwcfg.available_cubes())
            return
        # create the registry directory for this instance
        print '\n'+underline_title('Creating the instance %s' % appid)
        create_dir(config.apphome)
        # cubicweb-ctl configuration
        print '\n'+underline_title('Configuring the instance (%s.conf)' % configname)
        config.input_config('main', self.config.config_level)
        # configuration'specific stuff
        print
        helper.bootstrap(cubes, self.config.config_level)
        # input for cubes specific options
        for section in set(sect.lower() for sect, opt, optdict in config.all_options()
                           if optdict.get('inputlevel') <= self.config.config_level):
            if section not in ('main', 'email', 'pyro'):
                print '\n' + underline_title('%s options' % section)
                config.input_config(section, self.config.config_level)
        # write down configuration
        config.save()
        self._handle_win32(config, appid)
        print '-> generated %s' % config.main_config_file()
        # handle i18n files structure
        # in the first cube given
        print '-> preparing i18n catalogs'
        from cubicweb import i18n
        langs = [lang for lang, _ in i18n.available_catalogs(join(templdirs[0], 'i18n'))]
        errors = config.i18ncompile(langs)
        if errors:
            print '\n'.join(errors)
            if not ASK.confirm('error while compiling message catalogs, '
                               'continue anyway ?'):
                print 'creation not completed'
                return
        # create the additional data directory for this instance
        if config.appdatahome != config.apphome: # true in dev mode
            create_dir(config.appdatahome)
        create_dir(join(config.appdatahome, 'backup'))
        if config['uid']:
            from logilab.common.shellutils import chown
            # this directory should be owned by the uid of the server process
            print 'set %s as owner of the data directory' % config['uid']
            chown(config.appdatahome, config['uid'])
        print '\n-> creation done for %r.\n' % config.apphome
        helper.postcreate()

    def _handle_win32(self, config, appid):
        if sys.platform != 'win32':
            return
        service_template = """
import sys
import win32serviceutil
sys.path.insert(0, r"%(CWPATH)s")

from cubicweb.etwist.service import CWService

classdict = {'_svc_name_': 'cubicweb-%(APPID)s',
             '_svc_display_name_': 'CubicWeb ' + '%(CNAME)s',
             'instance': '%(APPID)s'}
%(CNAME)sService = type('%(CNAME)sService', (CWService,), classdict)

if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(%(CNAME)sService)
"""
        open(join(config.apphome, 'win32svc.py'), 'wb').write(
            service_template % {'APPID': appid,
                                'CNAME': appid.capitalize(),
                                'CWPATH': abspath(join(dirname(__file__), '..'))})


class DeleteInstanceCommand(Command):
    """Delete an instance. Will remove instance's files and
    unregister it.
    """
    name = 'delete'
    arguments = '<instance>'

    options = ()

    def run(self, args):
        """run the command with its specific arguments"""
        appid = pop_arg(args, msg="No instance specified !")
        configs = [cwcfg.config_for(appid, configname)
                   for configname in cwcfg.possible_configurations(appid)]
        if not configs:
            raise ExecutionError('unable to guess configuration for %s' % appid)
        for config in configs:
            helper = self.config_helper(config, required=False)
            if helper:
                helper.cleanup()
        # remove home
        rm(config.apphome)
        # remove instance data directory
        try:
            rm(config.appdatahome)
        except OSError, ex:
            import errno
            if ex.errno != errno.ENOENT:
                raise
        confignames = ', '.join([config.name for config in configs])
        print '-> instance %s (%s) deleted.' % (appid, confignames)


# instance commands ########################################################

class StartInstanceCommand(InstanceCommandFork):
    """Start the given instances. If no instance is given, start them all.

    <instance>...
      identifiers of the instances to start. If no instance is
      given, start them all.
    """
    name = 'start'
    actionverb = 'started'
    options = (
        ("debug",
         {'short': 'D', 'action' : 'store_true',
          'help': 'start server in debug mode.'}),
        ("force",
         {'short': 'f', 'action' : 'store_true',
          'default': False,
          'help': 'start the instance even if it seems to be already \
running.'}),
        ('profile',
         {'short': 'P', 'type' : 'string', 'metavar': '<stat file>',
          'default': None,
          'help': 'profile code and use the specified file to store stats',
          }),
        ('loglevel',
         {'short': 'l', 'type' : 'choice', 'metavar': '<log level>',
          'default': None, 'choices': ('debug', 'info', 'warning', 'error'),
          'help': 'debug if -D is set, error otherwise',
          }),
        )

    def start_instance(self, appid):
        """start the instance's server"""
        debug = self['debug']
        force = self['force']
        loglevel = self['loglevel']
        config = cwcfg.config_for(appid)
        if loglevel is not None:
            loglevel = 'LOG_%s' % loglevel.upper()
            config.global_set_option('log-threshold', loglevel)
            config.init_log(loglevel, debug=debug, force=True)
        if self['profile']:
            config.global_set_option('profile', self.config.profile)
        helper = self.config_helper(config, cmdname='start')
        pidf = config['pid-file']
        if exists(pidf) and not force:
            msg = "%s seems to be running. Remove %s by hand if necessary or use \
the --force option."
            raise ExecutionError(msg % (appid, pidf))
        helper.start_server(config, debug)


class StopInstanceCommand(InstanceCommand):
    """Stop the given instances.

    <instance>...
      identifiers of the instances to stop. If no instance is
      given, stop them all.
    """
    name = 'stop'
    actionverb = 'stopped'

    def ordered_instances(self):
        instances = super(StopInstanceCommand, self).ordered_instances()
        instances.reverse()
        return instances

    def stop_instance(self, appid):
        """stop the instance's server"""
        config = cwcfg.config_for(appid)
        helper = self.config_helper(config, cmdname='stop')
        helper.poststop() # do this anyway
        pidf = config['pid-file']
        if not exists(pidf):
            print >> sys.stderr, "%s doesn't exist." % pidf
            return
        import signal
        pid = int(open(pidf).read().strip())
        try:
            kill(pid, signal.SIGTERM)
        except:
            print >> sys.stderr, "process %s seems already dead." % pid
        else:
            try:
                wait_process_end(pid)
            except ExecutionError, ex:
                print >> sys.stderr, ex
                print >> sys.stderr, 'trying SIGKILL'
                try:
                    kill(pid, signal.SIGKILL)
                except:
                    # probably dead now
                    pass
                wait_process_end(pid)
        try:
            remove(pidf)
        except OSError:
            # already removed by twistd
            pass
        print 'instance %s stopped' % appid


class RestartInstanceCommand(StartInstanceCommand):
    """Restart the given instances.

    <instance>...
      identifiers of the instances to restart. If no instance is
      given, restart them all.
    """
    name = 'restart'
    actionverb = 'restarted'

    def run_args(self, args, askconfirm):
        regdir = cwcfg.registry_dir()
        if not isfile(join(regdir, 'startorder')) or len(args) <= 1:
            # no specific startorder
            super(RestartInstanceCommand, self).run_args(args, askconfirm)
            return
        print ('some specific start order is specified, will first stop all '
               'instances then restart them.')
        # get instances in startorder
        for appid in args:
            if askconfirm:
                print '*'*72
                if not ASK.confirm('%s instance %r ?' % (self.name, appid)):
                    continue
            StopInstanceCommand().stop_instance(appid)
        forkcmd = [w for w in sys.argv if not w in args]
        forkcmd[1] = 'start'
        forkcmd = ' '.join(forkcmd)
        for appid in reversed(args):
            status = system('%s %s' % (forkcmd, appid))
            if status:
                sys.exit(status)

    def restart_instance(self, appid):
        StopInstanceCommand().stop_instance(appid)
        self.start_instance(appid)


class ReloadConfigurationCommand(RestartInstanceCommand):
    """Reload the given instances. This command is equivalent to a
    restart for now.

    <instance>...
      identifiers of the instances to reload. If no instance is
      given, reload them all.
    """
    name = 'reload'

    def reload_instance(self, appid):
        self.restart_instance(appid)


class StatusCommand(InstanceCommand):
    """Display status information about the given instances.

    <instance>...
      identifiers of the instances to status. If no instance is
      given, get status information about all registered instances.
    """
    name = 'status'
    options = ()

    @staticmethod
    def status_instance(appid):
        """print running status information for an instance"""
        for mode in cwcfg.possible_configurations(appid):
            config = cwcfg.config_for(appid, mode)
            print '[%s-%s]' % (appid, mode),
            try:
                pidf = config['pid-file']
            except KeyError:
                print 'buggy instance, pid file not specified'
                continue
            if not exists(pidf):
                print "doesn't seem to be running"
                continue
            pid = int(open(pidf).read().strip())
            # trick to guess whether or not the process is running
            try:
                getpgid(pid)
            except OSError:
                print "should be running with pid %s but the process can not be found" % pid
                continue
            print "running with pid %s" % (pid)


class UpgradeInstanceCommand(InstanceCommandFork):
    """Upgrade an instance after cubicweb and/or component(s) upgrade.

    For repository update, you will be prompted for a login / password to use
    to connect to the system database.  For some upgrades, the given user
    should have create or alter table permissions.

    <instance>...
      identifiers of the instances to upgrade. If no instance is
      given, upgrade them all.
    """
    name = 'upgrade'
    actionverb = 'upgraded'
    options = InstanceCommand.options + (
        ('force-componant-version',
         {'short': 't', 'type' : 'csv', 'metavar': 'cube1=X.Y.Z,cube2=X.Y.Z',
          'default': None,
          'help': 'force migration from the indicated  version for the specified cube.'}),
        ('force-cubicweb-version',
         {'short': 'e', 'type' : 'string', 'metavar': 'X.Y.Z',
          'default': None,
          'help': 'force migration from the indicated cubicweb version.'}),

        ('fs-only',
         {'short': 's', 'action' : 'store_true',
          'default': False,
          'help': 'only upgrade files on the file system, not the database.'}),

        ('nostartstop',
         {'short': 'n', 'action' : 'store_true',
          'default': False,
          'help': 'don\'t try to stop instance before migration and to restart it after.'}),

        ('verbosity',
         {'short': 'v', 'type' : 'int', 'metavar': '<0..2>',
          'default': 1,
          'help': "0: no confirmation, 1: only main commands confirmed, 2 ask \
for everything."}),

        ('backup-db',
         {'short': 'b', 'type' : 'yn', 'metavar': '<y or n>',
          'default': None,
          'help': "Backup the instance database before upgrade.\n"\
          "If the option is ommitted, confirmation will be ask.",
          }),

        ('ext-sources',
         {'short': 'E', 'type' : 'csv', 'metavar': '<sources>',
          'default': None,
          'help': "For multisources instances, specify to which sources the \
repository should connect to for upgrading. When unspecified or 'migration' is \
given, appropriate sources for migration will be automatically selected \
(recommended). If 'all' is given, will connect to all defined sources.",
          }),
        )

    def upgrade_instance(self, appid):
        print '\n' + underline_title('Upgrading the instance %s' % appid)
        from logilab.common.changelog import Version
        config = cwcfg.config_for(appid)
        config.repairing = True # notice we're not starting the server
        config.verbosity = self.config.verbosity
        try:
            config.set_sources_mode(self.config.ext_sources or ('migration',))
        except AttributeError:
            # not a server config
            pass
        # get instance and installed versions for the server and the componants
        mih = config.migration_handler()
        repo = mih.repo_connect()
        vcconf = repo.get_versions()
        if self.config.force_componant_version:
            packversions = {}
            for vdef in self.config.force_componant_version:
                componant, version = vdef.split('=')
                packversions[componant] = Version(version)
            vcconf.update(packversions)
        toupgrade = []
        for cube in config.cubes():
            installedversion = config.cube_version(cube)
            try:
                applversion = vcconf[cube]
            except KeyError:
                config.error('no version information for %s' % cube)
                continue
            if installedversion > applversion:
                toupgrade.append( (cube, applversion, installedversion) )
        cubicwebversion = config.cubicweb_version()
        if self.config.force_cubicweb_version:
            applcubicwebversion = Version(self.config.force_cubicweb_version)
            vcconf['cubicweb'] = applcubicwebversion
        else:
            applcubicwebversion = vcconf.get('cubicweb')
        if cubicwebversion > applcubicwebversion:
            toupgrade.append(('cubicweb', applcubicwebversion, cubicwebversion))
        if not self.config.fs_only and not toupgrade:
            print '-> no software migration needed for instance %s.' % appid
            return
        for cube, fromversion, toversion in toupgrade:
            print '-> migration needed from %s to %s for %s' % (fromversion, toversion, cube)
        # only stop once we're sure we have something to do
        if not (CWDEV or self.config.nostartstop):
            StopInstanceCommand().stop_instance(appid)
        # run cubicweb/componants migration scripts
        mih.migrate(vcconf, reversed(toupgrade), self.config)
        # rewrite main configuration file
        mih.rewrite_configuration()
        # handle i18n upgrade:
        # * install new languages
        # * recompile catalogs
        # in the first componant given
        from cubicweb import i18n
        templdir = cwcfg.cube_dir(config.cubes()[0])
        langs = [lang for lang, _ in i18n.available_catalogs(join(templdir, 'i18n'))]
        errors = config.i18ncompile(langs)
        if errors:
            print '\n'.join(errors)
            if not ASK.confirm('Error while compiling message catalogs, '
                               'continue anyway ?'):
                print '-> migration not completed.'
                return
        mih.shutdown()
        print
        print '-> instance migrated.'
        if not (CWDEV or self.config.nostartstop):
            StartInstanceCommand().start_instance(appid)
        print


class ShellCommand(Command):
    """Run an interactive migration shell on an instance. This is a python shell
    with enhanced migration commands predefined in the namespace. An additional
    argument may be given corresponding to a file containing commands to execute
    in batch mode.

    By default it will connect to a local instance using an in memory
    connection, unless -P option is specified, in which case you will be
    connected through pyro. In the later case, you won't have access to
    repository internals (session, etc...) so most migration commands won't be
    available.

    <instance>
      the identifier of the instance to connect.
    """
    name = 'shell'
    arguments = '<instance> [batch command file]'
    options = (
        ('system-only',
         {'short': 'S', 'action' : 'store_true',
          'help': 'only connect to the system source when the instance is '
          'using multiple sources. You can\'t use this option and the '
          '--ext-sources option at the same time.',
          'group': 'local'
         }),

        ('ext-sources',
         {'short': 'E', 'type' : 'csv', 'metavar': '<sources>',
          'help': "For multisources instances, specify to which sources the \
repository should connect to for upgrading. When unspecified or 'all' given, \
will connect to all defined sources. If 'migration' is given, appropriate \
sources for migration will be automatically selected.",
          'group': 'local'
          }),

        ('force',
         {'short': 'f', 'action' : 'store_true',
          'help': 'don\'t check instance is up to date.',
          'group': 'local'
          }),

        ('pyro',
         {'short': 'P', 'action' : 'store_true',
          'help': 'connect to a running instance through Pyro.',
          'group': 'remote',
          }),
        ('pyro-ns-host',
         {'short': 'H', 'type' : 'string', 'metavar': '<host[:port]>',
          'help': 'Pyro name server host. If not set, will be detected by '
          'using a broadcast query.',
          'group': 'remote'
          }),
        )

    def run(self, args):
        appid = pop_arg(args, None, msg="No instance specified !")
        if self.config.pyro:
            from cubicweb import AuthenticationError
            from cubicweb.dbapi import connect
            from cubicweb.server.utils import manager_userpasswd
            from cubicweb.server.migractions import ServerMigrationHelper
            while True:
                try:
                    login, pwd = manager_userpasswd(msg=None)
                    cnx = connect(appid, login=login, password=pwd,
                                  host=self.config.pyro_ns_host, mulcnx=False)
                except AuthenticationError, ex:
                    print ex
                except (KeyboardInterrupt, EOFError):
                    print
                    sys.exit(0)
                else:
                    break
            cnx.load_appobjects()
            repo = cnx._repo
            mih = ServerMigrationHelper(None, repo=repo, cnx=cnx,
                                         # hack so it don't try to load fs schema
                                        schema=1)
        else:
            config = cwcfg.config_for(appid)
            if self.config.ext_sources:
                assert not self.config.system_only
                sources = self.config.ext_sources
            elif self.config.system_only:
                sources = ('system',)
            else:
                sources = ('all',)
            config.set_sources_mode(sources)
            config.repairing = self.config.force
            mih = config.migration_handler()
        try:
            if args:
                for arg in args:
                    mih.cmd_process_script(arg)
            else:
                mih.interactive_shell()
        finally:
            if not self.config.pyro:
                mih.shutdown()
            else:
                cnx.close()


class RecompileInstanceCatalogsCommand(InstanceCommand):
    """Recompile i18n catalogs for instances.

    <instance>...
      identifiers of the instances to consider. If no instance is
      given, recompile for all registered instances.
    """
    name = 'i18ninstance'

    @staticmethod
    def i18ninstance_instance(appid):
        """recompile instance's messages catalogs"""
        config = cwcfg.config_for(appid)
        config.repairing = True # notify this is not a regular start
        config.read_instance_schema = False # bootstrap schema is enough
        repo = config.repository()
        if config._cubes is None:
            # web only config
            config.init_cubes(repo.get_cubes())
        errors = config.i18ncompile()
        if errors:
            print '\n'.join(errors)


class ListInstancesCommand(Command):
    """list available instances, useful for bash completion."""
    name = 'listinstances'
    hidden = True

    def run(self, args):
        """run the command with its specific arguments"""
        regdir = cwcfg.registry_dir()
        for appid in sorted(listdir(regdir)):
            print appid


class ListCubesCommand(Command):
    """list available componants, useful for bash completion."""
    name = 'listcubes'
    hidden = True

    def run(self, args):
        """run the command with its specific arguments"""
        for cube in cwcfg.available_cubes():
            print cube

register_commands((ListCommand,
                   CreateInstanceCommand,
                   DeleteInstanceCommand,
                   StartInstanceCommand,
                   StopInstanceCommand,
                   RestartInstanceCommand,
                   ReloadConfigurationCommand,
                   StatusCommand,
                   UpgradeInstanceCommand,
                   ShellCommand,
                   RecompileInstanceCatalogsCommand,
                   ListInstancesCommand, ListCubesCommand,
                   ))


def run(args):
    """command line tool"""
    cwcfg.load_cwctl_plugins()
    main_run(args, """%%prog %s [options] %s

The CubicWeb swiss-knife.

%s"""
)

if __name__ == '__main__':
    run(sys.argv[1:])
