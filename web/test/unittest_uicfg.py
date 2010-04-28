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
# logilab-common is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with CubicWeb.  If not, see <http://www.gnu.org/licenses/>.
from cubicweb.devtools.testlib import CubicWebTC
from cubicweb.web import uicfg

abaa = uicfg.actionbox_appearsin_addmenu

class UICFGTC(CubicWebTC):

    def test_default_actionbox_appearsin_addmenu_config(self):
        self.failIf(abaa.etype_get('TrInfo', 'wf_info_for', 'object', 'CWUser'))

if __name__ == '__main__':
    from logilab.common.testlib import unittest_main
    unittest_main()
