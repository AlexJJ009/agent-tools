# Moved to the canonical repository

The Win11 proxy relay wrapper now has one source of truth:

<https://github.com/AlexJJ009/win11-proxy-relay>

This directory intentionally contains no copied runtime or installer code.
Deploy, test, and document the wrapper from a pinned commit of the private
repository. Machine-local settings, subscription data, databases, credentials,
generated configs, logs, and backups must remain outside Git.
