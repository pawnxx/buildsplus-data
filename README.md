# Builds+ data mirror

Public build lists and author ranks for the Builds+ Deadlock mod.

GitHub Pages serves the prepared files, and GitHub Actions refreshes them approximately every 15 minutes. Scheduled runs may be delayed by GitHub. The game-data collector stays on the existing server.

Only the `site` directory is deployed. Server credentials, keys, internal caches and private relay configuration are not included.

Historical Eternus labels describe a confirmed ranked-match observation during the preceding season, not a verified final season rank. Current ranks are kept separate.

The Pages URL ends with `/relay.html`. The mod needs a VPK configured to use that address.

If the source is temporarily unavailable, the refresh preserves the previously published hero packets and reports cached status. An unsuccessful refresh never overwrites the Pages deployment with incomplete data.

To enable publication, open **Settings → Pages**, then select **GitHub Actions** under **Source**. The workflow runs on updates, can be started manually, and refreshes on its schedule.
