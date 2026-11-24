# Regenerates every README screenshot from the synthetic demo snapshot: `vhs docs/screens.tape`
# (needs vhs, ttyd, ffmpeg). Add one Screenshot line per new tab.
# vhs needs an output file; the GIF is not used
Output "/tmp/mt-screens.gif"

Set Shell "bash"
Set FontSize 22
Set Width 1800
Set Height 1100
Set Padding 12
Set Theme { "name": "market-terminal", "black": "#1a1a19", "red": "#e66767", "green": "#3fb27f", "yellow": "#c98500", "blue": "#3987e5", "magenta": "#a98bd9", "cyan": "#4cb5c4", "white": "#c3c2b7", "brightBlack": "#6b6a64", "brightRed": "#e66767", "brightGreen": "#3fb27f", "brightYellow": "#c98500", "brightBlue": "#3987e5", "brightMagenta": "#a98bd9", "brightCyan": "#4cb5c4", "brightWhite": "#f0efec", "background": "#1a1a19", "foreground": "#f0efec", "selection": "#2e2d2b", "cursor": "#f0efec" }

Hide
Type "uv run mt --demo tests/fixtures/snapshot.json"
Enter
Wait+Screen@20s /Data for/
Sleep 1s
Show

Screenshot docs/img/screen-overview.png
Sleep 500ms

Right
Sleep 1500ms
Screenshot docs/img/screen-chart.png
Sleep 500ms

Type "y"
Sleep 1500ms
Screenshot docs/img/screen-chart-year.png
Sleep 500ms

Type "y"
Right
Sleep 1500ms
Screenshot docs/img/screen-movers.png
Sleep 500ms

Type "q"
Sleep 500ms
