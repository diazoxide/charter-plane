# The GitHub Actions runner trims leading whitespace BEFORE it recognise

_2026-09-25 · persistent_

The GitHub Actions runner trims leading whitespace BEFORE it recognises a workflow command (actions/runner src/Runner.Common/ActionCommand.cs, TryParseV2: message.TrimStart() then StartsWith('::'); verified 2026-09-15). So indenting untrusted text in a CI log does not neutralise '::warning', '::add-mask::' or '::stop-commands::' in it. When CI echoes test output or any other untrusted text, put a non-blank gutter such as '    | ' in front of every line.
