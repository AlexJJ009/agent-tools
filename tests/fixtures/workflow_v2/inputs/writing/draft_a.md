# Status-page MVP 1: cache behavior is visible

## Goal {#goal}
MVP 1 shows the most recent service observation and refreshes the display from
cache. The user needs to distinguish when the service was checked from when
the page was redrawn before deciding whether to add active probes in MVP 2.

## Current result {#progress}
The page now separates those two times. One initial probe produced a healthy
observation; a cached refresh advanced the display time while the server's
request count stayed at 1. A later explicit probe received HTTP 429. The page
showed that failure and retained the earlier success only as historical data.

## Choice and reason {#decisions}
We kept cached refresh for MVP 1 because that was the agreed behavior. This
avoids an upstream request on every redraw, but a redraw cannot establish
current service health. Active probing therefore needs its own MVP 2 criterion
and handling for rate limits.

## What the observations establish {#evidence}
The server recorded probe 1 as HTTP 200 at 1000; the display advanced from 1010
to 1020 without another server request. Probe 2 returned HTTP 429 at 1030; the
render at 1040 showed `unavailable`, last observation 1030, and last success
1000. These observations support the cache and failure-display checks for the
local fixture. They do not establish production reliability or outage coverage.

## Scope and remaining acceptance {#scope}
This was a loopback demonstration with no production release. The user accepted
the separate timestamp display. The 429 display passed the technical check,
but the user has not inspected it. Neither that feedback nor this report
accepts all checklist items.

## Next decision {#next_steps}
Show the 429 state to the user for that item's acceptance. Define the interval
and rate-limit behavior for MVP 2 before changing refresh to active probes.
