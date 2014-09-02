# copyright 2003-2011 LOGILAB S.A. (Paris, FRANCE), all rights reserved.
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
"""WSGI request adapter for cubicweb

NOTE: each docstring tagged with ``COME FROM DJANGO`` means that
the code has been taken (or adapted) from Djanco source code :
  http://www.djangoproject.com/

"""

__docformat__ = "restructuredtext en"

from StringIO import StringIO
from urllib import quote
from urlparse import parse_qs

from cubicweb.multipart import copy_file, parse_form_data
from cubicweb.web.request import CubicWebRequestBase
from cubicweb.wsgi import pformat, normalize_header


class CubicWebWsgiRequest(CubicWebRequestBase):
    """most of this code COMES FROM DJANGO
    """

    def __init__(self, environ, vreg):
        self.environ = environ
        self.path = environ['PATH_INFO']
        self.method = environ['REQUEST_METHOD'].upper()

        # content_length "may be empty or absent"
        try:
            length = int(environ['CONTENT_LENGTH'])
        except (KeyError, ValueError):
            length = 0
        # wsgi.input is not seekable, so copy the request contents to a temporary file
        if length < 100000:
            self.content = StringIO()
        else:
            self.content = tempfile.TemporaryFile()
        copy_file(environ['wsgi.input'], self.content, maxread=length)
        self.content.seek(0, 0)
        environ['wsgi.input'] = self.content

        headers_in = dict((normalize_header(k[5:]), v) for k, v in self.environ.items()
                          if k.startswith('HTTP_'))
        if 'CONTENT_TYPE' in environ:
            headers_in['Content-Type'] = environ['CONTENT_TYPE']
        https = environ["wsgi.url_scheme"] == 'https'
        if self.path.startswith('/https/'):
            self.path = self.path[6:]
            self.environ['PATH_INFO'] = self.path
            https = True

        post, files = self.get_posted_data()

        super(CubicWebWsgiRequest, self).__init__(vreg, https, post,
                                                  headers= headers_in)
        self.content = environ['wsgi.input']
        if files is not None:
            for key, part in files.iteritems():
                name = None
                if part.filename is not None:
                    name = unicode(part.filename, self.encoding)
                self.form[key] = (name, part.file)

    def __repr__(self):
        # Since this is called as part of error handling, we need to be very
        # robust against potentially malformed input.
        form = pformat(self.form)
        meta = pformat(self.environ)
        return '<CubicWebWsgiRequest\FORM:%s,\nMETA:%s>' % \
            (form, meta)

    ## cubicweb request interface ################################################

    def http_method(self):
        """returns 'POST', 'GET', 'HEAD', etc."""
        return self.method

    def relative_path(self, includeparams=True):
        """return the normalized path of the request (ie at least relative
        to the instance's root, but some other normalization may be needed
        so that the returned path may be used to compare to generated urls

        :param includeparams:
           boolean indicating if GET form parameters should be kept in the path
        """
        path = self.environ['PATH_INFO']
        path = path[1:] # remove leading '/'
        if includeparams:
            qs = self.environ.get('QUERY_STRING')
            if qs:
                return '%s?%s' % (path, qs)

        return path

    ## wsgi request helpers ###################################################

    def instance_uri(self):
        """Return the instance's base URI (no PATH_INFO or QUERY_STRING)

        see python2.5's wsgiref.util.instance_uri code
        """
        environ = self.environ
        url = environ['wsgi.url_scheme'] + '://'
        if environ.get('HTTP_HOST'):
            url += environ['HTTP_HOST']
        else:
            url += environ['SERVER_NAME']
            if environ['wsgi.url_scheme'] == 'https':
                if environ['SERVER_PORT'] != '443':
                    url += ':' + environ['SERVER_PORT']
            else:
                if environ['SERVER_PORT'] != '80':
                    url += ':' + environ['SERVER_PORT']
        url += quote(environ.get('SCRIPT_NAME') or '/')
        return url

    def get_full_path(self):
        return '%s%s' % (self.path, self.environ.get('QUERY_STRING', '') and ('?' + self.environ.get('QUERY_STRING', '')) or '')

    def is_secure(self):
        return 'wsgi.url_scheme' in self.environ \
            and self.environ['wsgi.url_scheme'] == 'https'

    def get_posted_data(self):
        # The WSGI spec says 'QUERY_STRING' may be absent.
        post = parse_qs(self.environ.get('QUERY_STRING', ''))
        files = None
        if self.method == 'POST':
            forms, files = parse_form_data(self.environ, strict=True,
                                           mem_limit=self.vreg.config['max-post-length'])
            post.update(forms)
        self.content.seek(0, 0)
        return post, files
