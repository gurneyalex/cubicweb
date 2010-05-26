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
from cubicweb.devtools.testlib import CubicWebTC
from cubicweb.devtools.htmlparser import DTDValidator


class LogFormTemplateTC(CubicWebTC):

    def _login_labels(self):
        valid = self.content_type_validators.get('text/html', DTDValidator)()
        req = self.request()
        req.cnx.anonymous_connection = True
        page = valid.parse_string(self.vreg['views'].main_template(self.request(), 'login'))
        req.cnx.anonymous_connection = False
        return page.find_tag('label')

    def test_label(self):
        self.set_option('allow-email-login', 'yes')
        self.assertEquals(self._login_labels(), ['login or email', 'password'])
        self.set_option('allow-email-login', 'no')
        self.assertEquals(self._login_labels(), ['login', 'password'])
