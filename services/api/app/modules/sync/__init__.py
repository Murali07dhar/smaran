"""Sync server module (Claude 1.4).

Deliberately empty: other modules import `app.modules.sync.changelog.record_change`,
and importing the router from here would create a circular import with
`app.modules.insights.pipeline`.
"""
