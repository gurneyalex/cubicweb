import os, os.path as osp
import signal
from tempfile import mkdtemp, NamedTemporaryFile, TemporaryFile
import tempfile
from Queue import Queue, Empty
from subprocess import Popen, check_call, CalledProcessError
from shutil import rmtree, copy as copyfile
from uuid import uuid4 

# imported by default to simplify further import statements
from logilab.common.testlib import unittest_main, with_tempdir, InnerTest

import os
import cubicweb
from cubicweb.view import StartupView
from cubicweb.web.controller import Controller
from cubicweb.devtools.httptest import CubicWebServerTC


class VerboseCalledProcessError(CalledProcessError):

    def __init__(self, returncode, command, stdout, stderr):
        super(VerboseCalledProcessError, self).__init__(returncode, command)
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self):
        str = [ super(VerboseCalledProcessError, self).__str__()]
        if self.stdout.strip():
            str.append('******************')
            str.append('* process stdout *')
            str.append('******************')
            str.append(self.stdout)
        if self.stderr.strip():
            str.append('******************')
            str.append('* process stderr *')
            str.append('******************')
            str.append(self.stderr)
        return '\n'.join(str)



class FirefoxHelper(object):

    profile_name_mask = 'PYTEST_PROFILE_%(uid)s'

    def __init__(self, url=None):
        self._process = None
        self._tmp_dir = mkdtemp()
        self._profile_data = {'uid': uuid4()}
        self._profile_name = self.profile_name_mask % self._profile_data
        fnull = open(os.devnull, 'w')
        stdout = TemporaryFile()
        stderr = TemporaryFile()
        try:
          check_call(['firefox', '-no-remote', '-CreateProfile',
                      '%s %s' % (self._profile_name, self._tmp_dir)],
                                stdout=stdout, stderr=stderr)
        except CalledProcessError, cpe:
            stdout.seek(0)
            stderr.seek(0)
            raise VerboseCalledProcessError(cpe.returncode, cpe.cmd, stdout.read(), stderr.read())


    def start(self, url):
        self.stop()
        fnull = open(os.devnull, 'w')
        self._process = Popen(['firefox', '-no-remote', '-P', self._profile_name, url],
                              stdout=fnull, stderr=fnull)

    def stop(self):
        if self._process is not None:
            assert self._process.returncode is None,  self._process.returncode
            os.kill(self._process.pid, signal.SIGTERM)
            self._process.wait()
            self._process = None

    def __del__(self):
        self.stop()
        rmtree(self._tmp_dir)


class QUnitTestCase(CubicWebServerTC):

    # testfile, (dep_a, dep_b)
    all_js_tests = ()

    def setUp(self):
        super(QUnitTestCase, self).setUp()
        self.test_queue = Queue()
        class MyQUnitResultController(QUnitResultController):
            tc = self
            test_queue = self.test_queue
        self._qunit_controller = MyQUnitResultController
        self.vreg.register(MyQUnitResultController)

    def tearDown(self):
        super(QUnitTestCase, self).tearDown()
        self.vreg.unregister(self._qunit_controller)


    def abspath(self, path):
        """use self.__module__ to build absolute path if necessary"""
        if not osp.isabs(path):
           dirname = osp.dirname(__import__(self.__module__).__file__)
           return osp.abspath(osp.join(dirname,path))
        return path



    def test_javascripts(self):
        for args in self.all_js_tests:
            test_file = self.abspath(args[0])
            if len(args) > 1:
                depends   = [self.abspath(dep) for dep in args[1]]
            else:
                depends = ()
            if len(args) > 2:
                data   = [self.abspath(data) for data in args[2]]
            else:
                data = ()
            for js_test in self._test_qunit(test_file, depends, data):
                yield js_test

    @with_tempdir
    def _test_qunit(self, test_file, depends=(), data_files=(), timeout=30):
        assert osp.exists(test_file), test_file
        for dep in depends:
            assert osp.exists(dep), dep
        for data in data_files:
            assert osp.exists(data), data


        # generate html test file
        html_test_file = NamedTemporaryFile(suffix='.html')
        html_test_file.write(make_qunit_html(test_file, depends,
                             server_data=(self.test_host, self.test_port)))
        html_test_file.flush()
        # copying data file
        for data in data_files:
            copyfile(data, tempfile.tempdir)

        while not self.test_queue.empty():
            self.test_queue.get(False)

        browser = FirefoxHelper()
        browser.start(html_test_file.name)
        test_count = 0
        error = False
        def raise_exception(cls, *data):
            raise cls(*data)
        while not error:
            try:
                result, test_name, msg = self.test_queue.get(timeout=timeout)
                test_name = '%s (%s)' % (test_name, test_file)
                self.set_description(test_name)
                if result is None:
                    break
                test_count += 1
                if result:
                    yield InnerTest(test_name, lambda : 1)
                else:
                    yield InnerTest(test_name, self.fail, msg)
            except Empty:
                error = True
                yield InnerTest(test_file, raise_exception, RuntimeError, "%s did not report execution end. %i test processed so far." % (test_file, test_count))

        browser.stop()
        if test_count <= 0 and not error:
            yield InnerTest(test_name, raise_exception, RuntimeError, 'No test yielded by qunit for %s' % test_file)

class QUnitResultController(Controller):

    __regid__ = 'qunit_result'


    # Class variables to circumvent the instantiation of a new Controller for each request.
    _log_stack = [] # store QUnit log messages
    _current_module_name = '' # store the current QUnit module name

    def publish(self, rset=None):
        event = self._cw.form['event']
        getattr(self, 'handle_%s' % event)()

    def handle_module_start(self):
        self.__class__._current_module_name = self._cw.form.get('name', '')

    def handle_test_done(self):
        name = '%s // %s' %  (self._current_module_name, self._cw.form.get('name', ''))
        failures = int(self._cw.form.get('failures', 0))
        total = int(self._cw.form.get('total', 0))

        self._log_stack.append('%i/%i assertions failed' % (failures, total))
        msg = '\n'.join(self._log_stack)

        if failures:
            self.tc.test_queue.put((False, name, msg))
        else:
            self.tc.test_queue.put((True, name, msg))
        self._log_stack[:] = []

    def handle_done(self):
        self.tc.test_queue.put((None, None, None))

    def handle_log(self):
        result = self._cw.form['result']
        message = self._cw.form['message']
        self._log_stack.append('%s: %s' % (result, message))



def cw_path(*paths):
  return file_path(osp.join(cubicweb.CW_SOFTWARE_ROOT, *paths))

def file_path(path):
    return 'file://' + osp.abspath(path)

def build_js_script( host, port):
    return """
    var host = '%s';
    var port = '%s';

    QUnit.moduleStart = function (name) {
      jQuery.ajax({
                  url: 'http://'+host+':'+port+'/qunit_result',
                 data: {"event": "module_start",
                        "name": name},
                 async: false});
    }

    QUnit.testDone = function (name, failures, total) {
      jQuery.ajax({
                  url: 'http://'+host+':'+port+'/qunit_result',
                 data: {"event": "test_done",
                        "name": name,
                        "failures": failures,
                        "total":total},
                 async: false});
    }

    QUnit.done = function (failures, total) {
      jQuery.ajax({
                   url: 'http://'+host+':'+port+'/qunit_result',
                   data: {"event": "done",
                          "failures": failures,
                          "total":total},
                   async: false});
      window.close();
    }

    QUnit.log = function (result, message) {
      jQuery.ajax({
                   url: 'http://'+host+':'+port+'/qunit_result',
                   data: {"event": "log",
                          "result": result,
                          "message": message},
                   async: false});
    }
    """ % (host, port)

def make_qunit_html(test_file, depends=(), server_data=None):
    """"""
    data = {
            'web_data': cw_path('web', 'data'),
            'web_test': cw_path('devtools', 'data'),
        }

    html = ['''<html>
  <head>
    <!-- JS lib used as testing framework -->
    <link rel="stylesheet" type="text/css" media="all" href="%(web_test)s/qunit.css" />
    <script src="%(web_data)s/jquery.js" type="text/javascript"></script>
    <script src="%(web_test)s/qunit.js" type="text/javascript"></script>'''
    % data]
    if server_data is not None:
        host, port = server_data
        html.append('<!-- result report tools -->')
        html.append('<script type="text/javascript">')
        html.append(build_js_script(host, port))
        html.append('</script>')
    html.append('<!-- Test script dependencies (tested code for example) -->')

    for dep in depends:
        html.append('    <script src="%s" type="text/javascript"></script>' % file_path(dep))

    html.append('    <!-- Test script itself -->')
    html.append('    <script src="%s" type="text/javascript"></script>'% (file_path(test_file),))
    html.append('''  </head>
  <body>
    <div id="main">
    </div>
    <h1 id="qunit-header">QUnit example</h1>
    <h2 id="qunit-banner"></h2>
    <h2 id="qunit-userAgent"></h2>
    <ol id="qunit-tests">
  </body>
</html>''')
    return u'\n'.join(html)







if __name__ == '__main__':
    unittest_main()
