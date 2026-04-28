# Project Constraints

- Linux and WSL2 machine bootstrap must persist tmux mouse mode for the Unix
  user running the tools. The durable config is a managed block in
  `${HOME}/.tmux.conf` containing `set -g mouse on`. Do not replace this with
  terminal-only scrollbar guidance; tmux scrolling must work through tmux mouse
  mode.
