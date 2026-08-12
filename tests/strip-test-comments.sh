#!/usr/bin/env bash
# Emit text with whole-line shell/Markdown comments and HTML comments removed.
strip_test_comments() {
  perl -0pe 's/<!--.*?-->//gs; s/^[ \t]*(?:#(?!#)|\/\/).*?(?:\n|$)//mg' "$1"
}
