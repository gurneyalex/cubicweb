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
"""web session component: by dfault the session is actually the db connection
object :/

"""
__docformat__ = "restructuredtext en"

from cubicweb.web import InvalidSession
from cubicweb.web.application import AbstractSessionManager


class InMemoryRepositorySessionManager(AbstractSessionManager):
    """manage session data associated to a session identifier"""

    def __init__(self, *args, **kwargs):
        AbstractSessionManager.__init__(self, *args, **kwargs)
        # XXX require a RepositoryAuthenticationManager which violates
        #     authenticate interface by returning a session instead of a user
        #assert isinstance(self.authmanager, RepositoryAuthenticationManager)
        self._sessions = {}

    # dump_data / restore_data to avoid loosing open sessions on registry
    # reloading
    def dump_data(self):
        return self._sessions
    def restore_data(self, data):
        self._sessions = data

    def current_sessions(self):
        return self._sessions.values()

    def get_session(self, req, sessionid):
        """return existing session for the given session identifier"""
        if not sessionid in self._sessions:
            raise InvalidSession()
        session = self._sessions[sessionid]
        if self.has_expired(session):
            self.close_session(session)
            raise InvalidSession()
        # give an opportunity to auth manager to hijack the session (necessary
        # with the RepositoryAuthenticationManager in case the connection to the
        # repository has expired)
        try:
            session = self.authmanager.validate_session(req, session)
            # necessary in case session has been hijacked
            self._sessions[session.sessionid] = session
        except InvalidSession:
            # invalid session
            del self._sessions[sessionid]
            raise
        return session

    def open_session(self, req):
        """open and return a new session for the given request

        :raise ExplicitLogin: if authentication is required
        """
        session = self.authmanager.authenticate(req)
        self._sessions[session.sessionid] = session
        return session

    def close_session(self, session):
        """close session on logout or on invalid session detected (expired out,
        corrupted...)
        """
        self.info('closing http session %s' % session)
        del self._sessions[session.sessionid]
        try:
            session.close()
        except:
            # already closed, may occurs if the repository session expired but
            # not the web session
            pass
