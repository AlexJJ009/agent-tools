# Local service status page

Start the loopback example with `python3 server.py --journal requests.jsonl`.
Its first output line contains the base URL. `/probe` returns a repeating
success, rate-limit, success sequence; `/stats` reports the probe count without
performing a probe. This server has no upstream connection.

`python3 page.py --base-url URL --state cache.json` renders a JSON page model.
Without a cache it obtains one observation. Later calls use the cache by
default. The `--mode probe` option takes a new observation before rendering.
Both the last observation time and the display refresh time are available in
the page model. `--timeout` sets the client wait in seconds, and `--endpoint
/slow` exercises a local slow response. `--effect` writes an inert sandbox
publication manifest containing the page model that was actually rendered.

This is a local status display demonstration, not a production health service.
