# src/pending_line.rs

**Role:** Items in `pending_updates.md`.

An item is `- path: message`; `file_of` also reads the older `- path — message` shape. `format_item` builds one line. `append_item` adds an item when the file is not listed yet and drops the `EMPTY_NOTE` line; `remove_item` drops a file's item and puts `EMPTY_NOTE` back when no item is left. `record_message` is the reason followed by "refresh the wiki, then mark-green". `CHECK_MESSAGE` is the text `check-changes` writes.
