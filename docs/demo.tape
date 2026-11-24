# The README demo video, from the synthetic demo snapshot: `vhs docs/demo.tape`
# (needs vhs, ttyd, ffmpeg). Writes docs/img/demo.gif and docs/img/demo.mp4.
Output docs/img/demo.gif
Output docs/img/demo.mp4

Set Shell "bash"
Set FontSize 22
Set Width 1800
Set Height 1100
Set Padding 12
Set Framerate 12
Set Theme { "name": "market-terminal", "black": "#1a1a19", "red": "#e66767", "green": "#3fb27f", "yellow": "#c98500", "blue": "#3987e5", "magenta": "#a98bd9", "cyan": "#4cb5c4", "white": "#c3c2b7", "brightBlack": "#6b6a64", "brightRed": "#e66767", "brightGreen": "#3fb27f", "brightYellow": "#c98500", "brightBlue": "#3987e5", "brightMagenta": "#a98bd9", "brightCyan": "#4cb5c4", "brightWhite": "#f0efec", "background": "#1a1a19", "foreground": "#f0efec", "selection": "#2e2d2b", "cursor": "#f0efec" }

Hide
Type "uv run mt --demo tests/fixtures/snapshot.json"
Enter
Wait+Screen@20s /Data for/
Sleep 1s
Show

Sleep 3s
Right
Sleep 3s
Type "y"
Sleep 2500ms
Type "y"
Sleep 1500ms
Right
Sleep 3s
Right
Sleep 3s
Right
Sleep 3s
Right
Sleep 2500ms
Down
Sleep 400ms
Down
Sleep 400ms
Enter
Sleep 4s
Escape
Sleep 1500ms
Type "q"
Sleep 1s
