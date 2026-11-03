//! Public names for wiki checks.
//! Python is a small tokenizer (strings, comments, and brackets), not a line scan.
//! JS/TS exports are read after comments and strings are masked.

use std::collections::BTreeSet;

/// `__all__` when it is a literal list or tuple (including `+=`), otherwise
/// top-level `def` / `async def` / `class` names that do not start with `_`.
pub fn python_public_symbols(text: &str) -> Vec<String> {
    let b = text.as_bytes();
    let mut i = 0;
    let mut depth = 0i32;
    let mut defs = BTreeSet::new();
    let mut exported: Option<BTreeSet<String>> = None;
    while i < b.len() {
        if depth == 0 && at_line_start(b, i) {
            let (col, j) = indent_at(b, i);
            if j >= b.len() {
                break;
            }
            if b[j] == b'#' {
                i = skip_line(b, j);
                continue;
            }
            if b[j] == b'\n' || b[j] == b'\r' {
                i = j + 1;
                continue;
            }
            if col == 0 {
                if starts_keyword(b, j, "__all__") {
                    let (names, next, replaced) = read_all_assignment(b, j);
                    if let Some(names) = names {
                        let set = exported.get_or_insert_with(BTreeSet::new);
                        if replaced {
                            set.clear();
                        }
                        set.extend(names);
                    }
                    i = next;
                    continue;
                }
                if let Some((name, next)) = read_top_def(b, j) {
                    if !name.starts_with('_') {
                        defs.insert(name);
                    }
                    i = next;
                    continue;
                }
            }
            i = j;
        }
        i = consume_one(b, i, &mut depth);
    }
    let chosen = exported.unwrap_or(defs);
    chosen.into_iter().collect()
}

/// Exported JS/TS names. Comments, strings, and template text do not count.
pub fn js_public_symbols(text: &str) -> Vec<String> {
    let masked = mask_js(text);
    let b = masked.as_bytes();
    let mut names = BTreeSet::new();
    let mut i = 0;
    while i < b.len() {
        if word_at(b, i, "export") {
            i += "export".len();
            i = skip_ws(b, i);
            if word_at(b, i, "default") {
                i += "default".len();
                i = skip_ws(b, i);
            }
            if word_at(b, i, "type") {
                let after = i + "type".len();
                let next = skip_ws(b, after);
                if b.get(next) == Some(&b'{') {
                    i = next;
                }
            }
            for word in ["declare", "abstract", "async"] {
                if word_at(b, i, word) {
                    i += word.len();
                    i = skip_ws(b, i);
                }
            }
            if b.get(i) == Some(&b'{') {
                i += 1;
                let end = b[i..]
                    .iter()
                    .position(|c| *c == b'}')
                    .map(|n| i + n)
                    .unwrap_or(b.len());
                for part in masked[i..end].split(',') {
                    let part = part.trim().trim_start_matches("type ").trim();
                    if part.is_empty() {
                        continue;
                    }
                    let name = part.split(" as ").last().unwrap_or(part).trim();
                    push_js(&mut names, name);
                }
                i = (end + 1).min(b.len());
                continue;
            }
            if b.get(i) == Some(&b'*') {
                i += 1;
                continue;
            }
            for kind in [
                "function",
                "class",
                "const",
                "let",
                "var",
                "interface",
                "enum",
                "namespace",
                "type",
            ] {
                if word_at(b, i, kind) {
                    i += kind.len();
                    if b.get(i) == Some(&b'*') {
                        i += 1;
                    }
                    i = skip_ws(b, i);
                    let (name, next) = read_js_ident(b, i);
                    push_js(&mut names, &name);
                    i = next;
                    break;
                }
            }
            continue;
        }
        i += 1;
    }
    names.into_iter().collect()
}

fn push_js(names: &mut BTreeSet<String>, name: &str) {
    let name = name
        .trim()
        .trim_matches(|c| c == '\'' || c == '"' || c == '`');
    if name.is_empty() || name == "default" || name == "from" || name.starts_with('_') {
        return;
    }
    if name
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '$')
    {
        names.insert(name.to_string());
    }
}

fn at_line_start(b: &[u8], i: usize) -> bool {
    i == 0 || b[i - 1] == b'\n'
}

fn indent_at(b: &[u8], mut i: usize) -> (usize, usize) {
    let mut col = 0;
    while i < b.len() && (b[i] == b' ' || b[i] == b'\t') {
        col += 1;
        i += 1;
    }
    (col, i)
}

fn skip_line(b: &[u8], mut i: usize) -> usize {
    while i < b.len() && b[i] != b'\n' {
        i += 1;
    }
    i
}

fn skip_ws(b: &[u8], mut i: usize) -> usize {
    while i < b.len() && b[i].is_ascii_whitespace() {
        i += 1;
    }
    i
}

fn starts_keyword(b: &[u8], i: usize, word: &str) -> bool {
    let w = word.as_bytes();
    i + w.len() <= b.len()
        && &b[i..i + w.len()] == w
        && !b.get(i + w.len()).is_some_and(|c| is_ident(*c))
}

fn word_at(b: &[u8], i: usize, word: &str) -> bool {
    if i > 0 && is_ident(b[i - 1]) {
        return false;
    }
    starts_keyword(b, i, word)
}

fn is_ident(c: u8) -> bool {
    c.is_ascii_alphanumeric() || c == b'_'
}

fn read_ident(b: &[u8], mut i: usize) -> (String, usize) {
    let start = i;
    while i < b.len() && is_ident(b[i]) {
        i += 1;
    }
    (String::from_utf8_lossy(&b[start..i]).into_owned(), i)
}

fn read_top_def(b: &[u8], i: usize) -> Option<(String, usize)> {
    let mut j = i;
    if starts_keyword(b, j, "async") {
        j = skip_ws(b, j + "async".len());
    }
    if starts_keyword(b, j, "def") || starts_keyword(b, j, "class") {
        let key = if starts_keyword(b, j, "def") {
            "def"
        } else {
            "class"
        };
        j = skip_ws(b, j + key.len());
        let (name, next) = read_ident(b, j);
        if name.is_empty() {
            return None;
        }
        return Some((name, next));
    }
    None
}

/// Returns names, the index after the statement's opening literal, and whether `=` replaced.
fn read_all_assignment(b: &[u8], i: usize) -> (Option<Vec<String>>, usize, bool) {
    let mut j = i + "__all__".len();
    j = skip_ws(b, j);
    let replaced = if b.get(j) == Some(&b'+') && b.get(j + 1) == Some(&b'=') {
        j += 2;
        false
    } else if b.get(j) == Some(&b'=') {
        j += 1;
        true
    } else {
        return (None, i + 1, false);
    };
    j = skip_ws(b, j);
    if b.get(j) != Some(&b'[') && b.get(j) != Some(&b'(') {
        return (None, j, replaced);
    }
    let (names, next) = collect_literal_strings(b, j);
    (Some(names), next, replaced)
}

fn collect_literal_strings(b: &[u8], mut i: usize) -> (Vec<String>, usize) {
    let mut depth = 0i32;
    let mut names = Vec::new();
    while i < b.len() {
        if let Some(next) = try_skip_string(b, i) {
            if depth == 1 {
                if let Some(text) = string_contents(b, i) {
                    names.push(text);
                }
            }
            i = next;
            continue;
        }
        if b[i] == b'#' {
            i = skip_line(b, i);
            continue;
        }
        match b[i] {
            b'(' | b'[' | b'{' => {
                depth += 1;
                i += 1;
            }
            b')' | b']' | b'}' => {
                depth -= 1;
                i += 1;
                if depth == 0 {
                    break;
                }
            }
            _ => i += 1,
        }
    }
    (names, i)
}

fn string_contents(b: &[u8], i: usize) -> Option<String> {
    let mut j = i;
    let mut pref = 0;
    while pref < 3 && j < b.len() && is_prefix_char(b[j]) {
        j += 1;
        pref += 1;
    }
    if j >= b.len() || (b[j] != b'\'' && b[j] != b'"') {
        return None;
    }
    let quote = b[j];
    let triple = b.get(j + 1) == Some(&quote) && b.get(j + 2) == Some(&quote);
    let start = if triple { j + 3 } else { j + 1 };
    let mut k = start;
    let mut out = Vec::new();
    if triple {
        while k + 2 < b.len() && !(b[k] == quote && b[k + 1] == quote && b[k + 2] == quote) {
            out.push(b[k]);
            k += 1;
        }
    } else {
        while k < b.len() && b[k] != quote && b[k] != b'\n' {
            if b[k] == b'\\' && k + 1 < b.len() {
                out.push(b[k + 1]);
                k += 2;
                continue;
            }
            out.push(b[k]);
            k += 1;
        }
    }
    Some(String::from_utf8_lossy(&out).into_owned())
}

fn consume_one(b: &[u8], i: usize, depth: &mut i32) -> usize {
    if i >= b.len() {
        return i;
    }
    if b[i] == b'#' {
        return skip_line(b, i);
    }
    if let Some(next) = try_skip_string(b, i) {
        return next;
    }
    match b[i] {
        b'(' | b'[' | b'{' => *depth += 1,
        b')' | b']' | b'}' => *depth -= 1,
        _ => {}
    }
    i + 1
}

fn is_prefix_char(c: u8) -> bool {
    matches!(c, b'r' | b'R' | b'b' | b'B' | b'f' | b'F' | b'u' | b'U')
}

fn try_skip_string(b: &[u8], i: usize) -> Option<usize> {
    if i > 0 && is_ident(b[i - 1]) && !is_prefix_char(b[i - 1]) {
        return None;
    }
    let mut j = i;
    let mut pref = 0;
    if i == 0 || !is_ident(b[i - 1]) {
        while pref < 3 && j < b.len() && is_prefix_char(b[j]) {
            j += 1;
            pref += 1;
        }
    }
    if j >= b.len() || (b[j] != b'\'' && b[j] != b'"') {
        return None;
    }
    if pref > 0 && i > 0 && is_ident(b[i - 1]) {
        return None;
    }
    Some(skip_quoted(b, j))
}

fn skip_quoted(b: &[u8], i: usize) -> usize {
    let quote = b[i];
    let triple = b.get(i + 1) == Some(&quote) && b.get(i + 2) == Some(&quote);
    let mut k = if triple { i + 3 } else { i + 1 };
    if triple {
        while k + 2 < b.len() && !(b[k] == quote && b[k + 1] == quote && b[k + 2] == quote) {
            k += 1;
        }
        (k + 3).min(b.len())
    } else {
        while k < b.len() && b[k] != quote && b[k] != b'\n' {
            if b[k] == b'\\' {
                k += 2;
                continue;
            }
            k += 1;
        }
        if k < b.len() && b[k] == quote {
            k + 1
        } else {
            k
        }
    }
}

fn read_js_ident(b: &[u8], mut i: usize) -> (String, usize) {
    let start = i;
    while i < b.len() {
        let c = b[i];
        if c.is_ascii_alphanumeric() || c == b'_' || c == b'$' {
            i += 1;
        } else {
            break;
        }
    }
    (String::from_utf8_lossy(&b[start..i]).into_owned(), i)
}

fn mask_js(text: &str) -> String {
    let b = text.as_bytes();
    let mut out = vec![b' '; b.len()];
    mask_range(b, &mut out, 0, false);
    String::from_utf8(out).unwrap_or_else(|_| text.to_string())
}

/// Copy code into `out`. When `stop_on_brace` is set, return at the `}` that
/// closes a `${ ... }` expression.
fn mask_range(b: &[u8], out: &mut [u8], mut i: usize, stop_on_brace: bool) -> usize {
    let mut brace = 0i32;
    while i < b.len() {
        if b[i] == b'\n' {
            out[i] = b'\n';
            i += 1;
            continue;
        }
        if b[i] == b'/' && i + 1 < b.len() && b[i + 1] == b'/' {
            while i < b.len() && b[i] != b'\n' {
                i += 1;
            }
            continue;
        }
        if b[i] == b'/' && i + 1 < b.len() && b[i + 1] == b'*' {
            i += 2;
            while i + 1 < b.len() && !(b[i] == b'*' && b[i + 1] == b'/') {
                i += 1;
            }
            i = (i + 2).min(b.len());
            continue;
        }
        if b[i] == b'\'' || b[i] == b'"' {
            let quote = b[i];
            i += 1;
            while i < b.len() && b[i] != quote && b[i] != b'\n' {
                if b[i] == b'\\' {
                    i = (i + 2).min(b.len());
                    continue;
                }
                i += 1;
            }
            if i < b.len() && b[i] == quote {
                i += 1;
            }
            continue;
        }
        if b[i] == b'`' {
            i += 1;
            while i < b.len() && b[i] != b'`' {
                if b[i] == b'$' && i + 1 < b.len() && b[i + 1] == b'{' {
                    out[i] = b[i];
                    out[i + 1] = b[i + 1];
                    i = mask_range(b, out, i + 2, true);
                    continue;
                }
                if b[i] == b'\\' {
                    i = (i + 2).min(b.len());
                    continue;
                }
                i += 1;
            }
            if i < b.len() && b[i] == b'`' {
                i += 1;
            }
            continue;
        }
        if b[i] == b'{' {
            brace += 1;
            out[i] = b[i];
            i += 1;
            continue;
        }
        if b[i] == b'}' {
            if stop_on_brace && brace == 0 {
                return i + 1;
            }
            if brace > 0 {
                brace -= 1;
            }
            out[i] = b[i];
            i += 1;
            continue;
        }
        out[i] = b[i];
        i += 1;
    }
    i
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn multiline_all_tuple_plus_and_hidden_defs() {
        let text = "\
__all__ = [
    \"visible\",
    # \"nope\"
    'also',
]
__all__ += (\"extra\",)
def hidden():
    return 1
def _private():
    return 2
";
        assert_eq!(
            python_public_symbols(text),
            vec![
                "also".to_string(),
                "extra".to_string(),
                "visible".to_string()
            ]
        );
    }

    #[test]
    fn decorators_async_and_strings_do_not_invent_names() {
        let text = "\
# def ghost():
s = \"def fake():\"
'''
def doc():
    pass
'''
@decorator
async def real():
    def inner():
        return 1
class Shown:
    def method(self):
        return 1
";
        assert_eq!(
            python_public_symbols(text),
            vec!["Shown".to_string(), "real".to_string()]
        );
    }

    #[test]
    fn js_ignores_comments_and_strings() {
        let text = "\
// export function ghost() {}
const s = \"export function fake() {}\";
/* export function block() {} */
export function real() {}
export { kept as publicName, type Kind }
";
        assert_eq!(
            js_public_symbols(text),
            vec![
                "Kind".to_string(),
                "publicName".to_string(),
                "real".to_string()
            ]
        );
    }
}
