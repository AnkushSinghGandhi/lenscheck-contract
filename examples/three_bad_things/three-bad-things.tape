# Render the money-shot GIF:  vhs three-bad-things.tape
# Install vhs: https://github.com/charmbracelet/vhs

Output three-bad-things.gif

Set Shell bash
Set FontFamily "JetBrains Mono"
Set FontSize 20
Set Width 1100
Set Height 900
Set Padding 28
Set Theme "Catppuccin Mocha"
Set TypingSpeed 40ms

Hide
Type "cd $(git rev-parse --show-toplevel)" Enter
Show

Type "bash examples/three_bad_things/run.sh" Sleep 500ms Enter
Sleep 6s
