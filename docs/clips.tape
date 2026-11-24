# Footage for the README demo video, from the synthetic demo snapshot: `vhs docs/clips.tape`
# (needs vhs, ttyd, ffmpeg). Writes one MP4 with seven segments; tab switches happen while hidden,
# so each segment starts cleanly on its tab. video/src/clips.ts holds where each segment starts.
# The video itself is composed in video/ (Remotion); see the README section "Regenerating the demo".
Output video/public/clips/session.mp4

Set Shell "bash"
Set FontSize 21
Set Width 1760
Set Height 880
Set Padding 10
Set Framerate 30
Set Theme { "name": "market-terminal", "black": "#1a1a19", "red": "#e66767", "green": "#3fb27f", "yellow": "#c98500", "blue": "#3987e5", "magenta": "#a98bd9", "cyan": "#4cb5c4", "white": "#c3c2b7", "brightBlack": "#6b6a64", "brightRed": "#e66767", "brightGreen": "#3fb27f", "brightYellow": "#c98500", "brightBlue": "#3987e5", "brightMagenta": "#a98bd9", "brightCyan": "#4cb5c4", "brightWhite": "#f0efec", "background": "#1a1a19", "foreground": "#f0efec", "selection": "#2e2d2b", "cursor": "#f0efec" }

Hide
Type "uv run mt --demo tests/fixtures/snapshot.json"
Enter
Wait+Screen@20s /Data for/
Sleep 1s
Show

# 1 Overview (hook + Overview)
Sleep 7500ms
Hide
Right
Sleep 1500ms
Show

# 2 Chart, then y for the whole year
Sleep 2000ms
Type "y"
Sleep 3500ms
Hide
Type "y"
Right
Sleep 1500ms
Show

# 3 Movers
Sleep 4500ms
Hide
Right
Sleep 1500ms
Show

# 4 Breadth
Sleep 4500ms
Hide
Right
Sleep 1500ms
Show

# 5 Sectors
Sleep 5500ms
Hide
Right
Sleep 1500ms
Show

# 6 Watchlist, then Enter on a stock
Sleep 2000ms
Down
Sleep 400ms
Down
Sleep 400ms
Enter
Sleep 3500ms
Hide
Escape
Sleep 1000ms
Show

# 7 Quit: q returns to the shell
Sleep 1000ms
Type "q"
Sleep 3000ms
