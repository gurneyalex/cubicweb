# copyright 2003-2012 LOGILAB S.A. (Paris, FRANCE), all rights reserved.
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
"""core hooks registering some maintainance tasks as server startup time"""

__docformat__ = "restructuredtext en"

from datetime import timedelta, datetime

from cubicweb.server import hook

class TransactionsCleanupStartupHook(hook.Hook):
    """start task to cleanup transaction data"""
    __regid__ = 'cw.looping-tasks.transactions-cleanup'
    events = ('server_startup',)

    def __call__(self):
        # XXX use named args and inner functions to avoid referencing globals
        # which may cause reloading pb
        lifetime = timedelta(days=self.repo.config['keep-transaction-lifetime'])
        def cleanup_old_transactions(repo=self.repo, lifetime=lifetime):
            mindate = datetime.now() - lifetime
            session = repo.internal_session()
            try:
                session.system_sql(
                    'DELETE FROM transactions WHERE tx_time < %(time)s',
                    {'time': mindate})
                # cleanup deleted entities
                session.system_sql(
                    'DELETE FROM deleted_entities WHERE dtime < %(time)s',
                    {'time': mindate})
                session.commit()
            finally:
                session.close()
        if self.repo.config['undo-enabled']:
            self.repo.looping_task(60*60*24, cleanup_old_transactions,
                                   self.repo)

class UpdateFeedsStartupHook(hook.Hook):
    """start task to update datafeed based sources"""
    __regid__ = 'cw.looping-tasks.update-feeds'
    events = ('server_startup',)

    def __call__(self):
        def update_feeds(repo):
            # don't iter on repo.sources which doesn't include copy based
            # sources (the one we're looking for)
            for source in repo.sources_by_eid.itervalues():
                if (not source.copy_based_source
                    or not repo.config.source_enabled(source)
                    or not source.config['synchronize']):
                    continue
                session = repo.internal_session(safe=True)
                try:
                    source.pull_data(session)
                except Exception, exc:
                    session.exception('while trying to update feed %s', source)
                finally:
                    session.close()
        self.repo.looping_task(60, update_feeds, self.repo)


class DataImportsCleanupStartupHook(hook.Hook):
    """start task to cleanup old data imports (ie datafeed import logs)"""
    __regid__ = 'cw.looping-tasks.dataimports-cleanup'
    events = ('server_startup',)

    def __call__(self):
        def expire_dataimports(repo=self.repo):
            for source in repo.sources_by_eid.itervalues():
                if (not source.copy_based_source
                    or not repo.config.source_enabled(source)):
                    continue
                session = repo.internal_session()
                try:
                    mindate = datetime.now() - timedelta(seconds=source.config['logs-lifetime'])
                    session.execute('DELETE CWDataImport X WHERE X start_timestamp < %(time)s',
                                    {'time': mindate})
                    session.commit()
                finally:
                    session.close()
        self.repo.looping_task(60*60*24, expire_dataimports, self.repo)
