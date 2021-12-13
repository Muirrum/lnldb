from crispy_forms.layout import HTML

markdown_msgs = HTML(
    '<div class="help-block muted offset2"><i class="icon-chevron-up"></i>'
    ' This field supports <a href="http://daringfireball.net/projects/markdown/basics">Markdown</a></div>')
markdown_at_msgs = HTML(
    '<div class="help-block muted offset2"><i class="icon-chevron-up"></i>'
    ' This field supports <a href="http://daringfireball.net/projects/markdown/basics">Markdown</a>'
    ' and Twitter style @username @eventid linking</div>')
at_msgs = HTML(
    '<div class="help-block muted offset2"><i class="icon-chevron-up"></i>'
    ' This field support Twitter style @username @eventid linking</div>')
slack_channel_msgs = HTML(
    '<div class="help-block muted offset2"><i class="icon-chevron-up"></i>'
    ' This field supports automatic Slack channel linking (i.e. #general)</div>')
