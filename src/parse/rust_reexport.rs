//! Rust re-exports: which file defines a name that a path reaches through a module's
//! `use` items. `use sp_input::Input;` lands in `sp_input`'s `lib.rs`; its
//! `pub use input::Input;` names `input.rs`, so the importer also gets an edge there.
//!
//! The scan side reads a file's top-level `use` items and item names. The lookup side
//! follows them, named items before globs, for up to [`RUST_GLOB_DEPTH`] hops.

use std::collections::{BTreeSet, HashMap, HashSet};
use std::path::Path;
use std::rc::Rc;

use super::{
    read_ident, scan_file, skip_noise, skip_restricted_pub, skip_rust_char_or_lifetime,
    skip_rust_comment, skip_rust_string, starts_word, Resolver, RustUse, Scan, RUST_GLOB_DEPTH,
};

/// The item a top-level token at `i` starts: its name, whether it carries any `pub`, and
/// where the name ends. `use`, `mod`, `impl`, `extern crate`, and macros are not items
/// here.
pub(super) fn item_def(b: &[u8], i: usize) -> Option<(String, bool, usize)> {
    let mut j = i;
    let public = starts_word(b, j, "pub");
    if public {
        j = skip_noise(b, skip_restricted_pub(b, j));
    }
    loop {
        if starts_word(b, j, "async") || starts_word(b, j, "unsafe") {
            j = skip_noise(b, j + if starts_word(b, j, "async") { 5 } else { 6 });
            continue;
        }
        if starts_word(b, j, "extern") {
            // `extern "C" fn f`; `extern crate x` and `extern "C" { ... }` name nothing here.
            let mut k = skip_noise(b, j + 6);
            if let Some(end) = skip_rust_string(b, k) {
                k = skip_noise(b, end);
            }
            if !starts_word(b, k, "fn") {
                return None;
            }
            j = k;
            continue;
        }
        if starts_word(b, j, "const") {
            let next = skip_noise(b, j + 5);
            if starts_word(b, next, "fn")
                || starts_word(b, next, "unsafe")
                || starts_word(b, next, "async")
                || starts_word(b, next, "extern")
            {
                j = next;
                continue;
            }
            let (name, end) = read_ident(b, next)?;
            return (name != "_").then_some((name, public, end));
        }
        break;
    }
    // `mod` is left out: a module's file is found by its path, not through a lookup.
    for word in ["fn", "struct", "enum", "union", "trait", "type", "static"] {
        if starts_word(b, j, word) {
            let mut next = skip_noise(b, j + word.len());
            if word == "static" && starts_word(b, next, "mut") {
                next = skip_noise(b, next + 3);
            }
            let (name, end) = read_ident(b, next)?;
            return Some((name, public, end));
        }
    }
    None
}

/// The names one `use` item binds, read from just after the `use` keyword.
pub(super) fn use_entries(b: &[u8], start: usize, public: bool) -> Vec<RustUse> {
    let mut out = Vec::new();
    let _ = walk(b, skip_noise(b, start), &[], public, &mut out);
    out
}

fn walk(
    b: &[u8],
    start: usize,
    prefix: &[String],
    public: bool,
    out: &mut Vec<RustUse>,
) -> Option<usize> {
    let i = skip_noise(b, start);
    if i >= b.len() {
        return None;
    }
    if b[i] == b'{' {
        let mut i = i + 1;
        loop {
            i = skip_noise(b, i);
            if i >= b.len() {
                return None;
            }
            if b[i] == b'}' {
                return Some(i + 1);
            }
            if b[i] == b',' {
                i += 1;
                continue;
            }
            i = walk(b, i, prefix, public, out)?;
        }
    }
    if b[i] == b'*' {
        out.push(RustUse {
            name: String::new(),
            path: prefix.join("::"),
            glob: true,
            public,
        });
        return Some(i + 1);
    }
    let (ident, mut j) = read_ident(b, i)?;
    j = skip_noise(b, j);
    let mut alias = None;
    if starts_word(b, j, "as") {
        let (name, after) = read_ident(b, skip_noise(b, j + 2))?;
        alias = Some(name);
        j = skip_noise(b, after);
    }
    if j + 1 < b.len() && b[j] == b':' && b[j + 1] == b':' {
        let mut deeper = prefix.to_vec();
        if ident != "self" {
            deeper.push(ident);
        }
        return walk(b, j + 2, &deeper, public, out);
    }
    let mut segs = prefix.to_vec();
    let bound = if ident == "self" {
        alias.or_else(|| prefix.last().cloned())
    } else {
        segs.push(ident.clone());
        alias.or(Some(ident))
    };
    if let Some(name) = bound.filter(|name| name != "_" && !segs.is_empty()) {
        out.push(RustUse {
            name,
            path: segs.join("::"),
            glob: false,
            public,
        });
    }
    Some(j)
}

/// Identifiers a file names on their own: comments, strings, and names after `.` or `::`
/// (fields, methods, qualified paths) are left out. A glob import brings a name into
/// scope; one of these is how the file uses it.
pub(super) fn bare_idents(text: &str) -> HashSet<String> {
    let b = text.as_bytes();
    let mut out = HashSet::new();
    let mut i = 0;
    let mut qualified = false;
    while i < b.len() {
        let c = b[i];
        if c.is_ascii_whitespace() {
            i += 1;
            continue;
        }
        if c == b'/' && i + 1 < b.len() && (b[i + 1] == b'/' || b[i + 1] == b'*') {
            i = skip_rust_comment(b, i);
            continue;
        }
        if let Some(end) = skip_rust_string(b, i) {
            i = end;
            qualified = false;
            continue;
        }
        if c == b'\'' {
            i = skip_rust_char_or_lifetime(b, i);
            qualified = false;
            continue;
        }
        if let Some((ident, end)) = read_ident(b, i) {
            if !qualified {
                out.insert(ident);
            }
            qualified = false;
            i = end;
            continue;
        }
        qualified = c == b'.' || (c == b':' && i > 0 && b[i - 1] == b':');
        if c.is_ascii_digit() {
            // A number such as `1.5` or `0xff`: its letters are not names.
            while i < b.len() && (b[i].is_ascii_alphanumeric() || b[i] == b'_') {
                i += 1;
            }
            continue;
        }
        i += 1;
    }
    out
}

/// What a file offers through `use` items and item names, one sorted entry each. An entry
/// starts with the name it binds (`*` for a glob), then a space. When the entries for a
/// name change, files that looked that name up here must be resolved again.
pub fn export_entries(scan: &Scan) -> Vec<String> {
    let mut out: Vec<String> = scan
        .rust_uses
        .iter()
        .map(|entry| {
            let key = if entry.glob { "*" } else { entry.name.as_str() };
            format!("{key} u {} {} {}", entry.path, entry.glob, entry.public)
        })
        .chain(
            scan.rust_defs
                .iter()
                .map(|(name, public)| format!("{name} d {public}")),
        )
        .collect();
    out.sort();
    out.dedup();
    out
}

/// One module's side of a lookup: its item names and its `use` items, with globs
/// resolved to the module file they name.
struct Table {
    defs: HashMap<String, bool>,
    named: Vec<RustUse>,
    globs: Vec<(String, bool)>,
}

/// A lookup's answer. `TooDeep` (the hop limit ran out) adds no edge, where `Missing`
/// after a named `use` falls back to the module that `use` names.
#[derive(Clone)]
enum Lookup {
    Found(String),
    Missing,
    TooDeep,
}

/// Names a glob of a module brings in, each with the file that defines it.
type Offer = Rc<Vec<(String, String)>>;

/// Per-run memory: each module's table, and each lookup's answer.
pub(super) struct Exports<'a> {
    root: &'a Path,
    resolver: &'a Resolver,
    known: &'a HashMap<String, Scan>,
    tables: HashMap<String, Rc<Table>>,
    definers: HashMap<(String, String, bool, usize), Lookup>,
    offers: HashMap<(String, bool, usize), Offer>,
}

impl<'a> Exports<'a> {
    pub(super) fn new(
        root: &'a Path,
        resolver: &'a Resolver,
        known: &'a HashMap<String, Scan>,
    ) -> Self {
        Exports {
            root,
            resolver,
            known,
            tables: HashMap::new(),
            definers: HashMap::new(),
            offers: HashMap::new(),
        }
    }

    fn table(&mut self, module: &str) -> Rc<Table> {
        if let Some(table) = self.tables.get(module) {
            return table.clone();
        }
        let fresh;
        let scan = match self.known.get(module) {
            Some(scan) => scan,
            None => {
                fresh = scan_file(&self.root.join(module));
                &fresh
            }
        };
        let mut defs = HashMap::new();
        for (name, public) in &scan.rust_defs {
            defs.entry(name.clone()).or_insert(*public);
        }
        let named = scan
            .rust_uses
            .iter()
            .filter(|entry| !entry.glob)
            .cloned()
            .collect();
        let globs = scan
            .rust_uses
            .iter()
            .filter(|entry| entry.glob)
            .filter_map(|entry| {
                match self.resolver.rust_lookup(module, &entry.path, 0) {
                    // A glob of an enum or a type (`use Kind::*`) brings in its members,
                    // not a module's names.
                    Some((file, None)) if file != module => Some((file, entry.public)),
                    _ => None,
                }
            })
            .collect();
        let table = Rc::new(Table { defs, named, globs });
        self.tables.insert(module.to_string(), table.clone());
        table
    }

    /// The file that defines `name` as seen from `module`. `private` lets the lookup use
    /// items without `pub` (the importer is inside the same crate). A named `use` that
    /// reaches a module with no such item ends at that module. A chain longer than
    /// [`RUST_GLOB_DEPTH`] hops has no answer.
    pub(super) fn definer(
        &mut self,
        module: &str,
        name: &str,
        private: bool,
        hops: usize,
    ) -> Option<String> {
        match self.lookup(module, name, private, hops) {
            Lookup::Found(file) => Some(file),
            Lookup::Missing | Lookup::TooDeep => None,
        }
    }

    fn lookup(&mut self, module: &str, name: &str, private: bool, hops: usize) -> Lookup {
        if hops > RUST_GLOB_DEPTH {
            return Lookup::TooDeep;
        }
        let key = (module.to_string(), name.to_string(), private, hops);
        if let Some(found) = self.definers.get(&key) {
            return found.clone();
        }
        let found = self.find(module, name, private, hops);
        self.definers.insert(key, found.clone());
        found
    }

    fn find(&mut self, module: &str, name: &str, private: bool, hops: usize) -> Lookup {
        let table = self.table(module);
        if let Some(public) = table.defs.get(name) {
            return if *public || private {
                Lookup::Found(module.to_string())
            } else {
                Lookup::Missing
            };
        }
        if let Some(entry) = table
            .named
            .iter()
            .find(|entry| entry.name == name && (entry.public || private))
        {
            return match self.resolver.rust_lookup(module, &entry.path, 0) {
                Some((file, None)) => Lookup::Found(file),
                Some((file, Some(inner))) if file != module => {
                    match self.lookup(&file, &inner, true, hops + 1) {
                        // Defined by a macro, behind `cfg`, or not read: the module the
                        // `use` names is the best answer.
                        Lookup::Missing => Lookup::Found(file),
                        other => other,
                    }
                }
                _ => Lookup::Missing,
            };
        }
        let mut answer = Lookup::Missing;
        for (glob, public) in &table.globs {
            if *public || private {
                match self.lookup(glob, name, false, hops + 1) {
                    Lookup::Found(file) => return Lookup::Found(file),
                    Lookup::TooDeep => answer = Lookup::TooDeep,
                    Lookup::Missing => {}
                }
            }
        }
        answer
    }

    /// Every name a glob import of `module` brings in, with the file that defines it.
    /// Item names and named `use` items come before the names of nested globs.
    pub(super) fn offered(&mut self, module: &str, private: bool, hops: usize) -> Offer {
        let key = (module.to_string(), private, hops);
        if let Some(found) = self.offers.get(&key) {
            return found.clone();
        }
        let table = self.table(module);
        let mut seen: BTreeSet<String> = BTreeSet::new();
        let mut out: Vec<(String, String)> = Vec::new();
        // A name the module binds itself hides the same name from its globs, even when
        // the importer cannot see it.
        for (name, public) in &table.defs {
            if seen.insert(name.clone()) && (*public || private) {
                out.push((name.clone(), module.to_string()));
            }
        }
        for entry in &table.named {
            if seen.insert(entry.name.clone()) && (entry.public || private) {
                if let Some(found) = self.definer(module, &entry.name, private, hops) {
                    out.push((entry.name.clone(), found));
                }
            }
        }
        if hops < RUST_GLOB_DEPTH {
            for (glob, public) in &table.globs {
                if !(*public || private) {
                    continue;
                }
                for (name, found) in self.offered(glob, false, hops + 1).iter() {
                    if seen.insert(name.clone()) {
                        out.push((name.clone(), found.clone()));
                    }
                }
            }
        }
        out.sort();
        let out = Rc::new(out);
        self.offers.insert(key, out.clone());
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entries(src: &str) -> Vec<(String, String, bool)> {
        let b = src.as_bytes();
        use_entries(b, 3, true)
            .into_iter()
            .map(|entry| (entry.name, entry.path, entry.glob))
            .collect()
    }

    #[test]
    fn use_items_bind_their_alias_or_last_segment() {
        assert_eq!(
            entries("use m::{A, B as C, inner::*, self as m2, _x as _};"),
            vec![
                ("A".into(), "m::A".into(), false),
                ("C".into(), "m::B".into(), false),
                (String::new(), "m::inner".into(), true),
                ("m2".into(), "m".into(), false),
            ]
        );
        assert_eq!(
            entries("use self::input::Input;"),
            vec![("Input".into(), "input::Input".into(), false)]
        );
    }

    #[test]
    fn item_names_skip_qualifiers_and_keep_visibility() {
        let check = |src: &str| item_def(src.as_bytes(), 0).map(|(name, public, _)| (name, public));
        assert_eq!(check("pub struct Input {"), Some(("Input".into(), true)));
        assert_eq!(check("pub(crate) const fn f()"), Some(("f".into(), true)));
        assert_eq!(
            check("pub unsafe extern \"C\" fn g()"),
            Some(("g".into(), true))
        );
        assert_eq!(check("static mut COUNT: u8"), Some(("COUNT".into(), false)));
        assert_eq!(check("const _: () = ();"), None);
        assert_eq!(check("extern crate alloc;"), None);
        assert_eq!(check("pub use a::B;"), None);
        assert_eq!(check("pub mod sight;"), None);
    }

    #[test]
    fn bare_idents_leave_out_fields_methods_paths_comments_and_strings() {
        let names =
            bare_idents("let r = x.record(); y::Other; Input::new(); // Gone\n\"Str\"; 1.5e3f32");
        assert!(names.contains("Input") && names.contains("x") && names.contains("y"));
        for absent in ["record", "Other", "new", "Gone", "Str", "e3f32"] {
            assert!(!names.contains(absent), "{absent} in {names:?}");
        }
    }
}
