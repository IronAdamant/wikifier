//! Import extraction for the languages Python Wikifier parses.
//! Unknown suffixes (COBOL, Swift, assembly) are not languages and emit no edges.

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fs;
use std::path::{Path, PathBuf};

use crate::jsonutil::{self, Json};
use crate::scope::rel_of;

#[derive(Clone, Debug)]
pub struct RawImport {
    pub spec: String,
    pub names: Vec<String>,
    pub kind: Kind,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    Import,
    ExportFrom,
    ExportStar,
    Dynamic,
}

#[derive(Clone, Debug, Default)]
pub struct Scan {
    pub imports: Vec<RawImport>,
    pub local_exports: Vec<String>,
}

pub fn language(path: &Path) -> Option<&'static str> {
    let name = path.file_name()?.to_str()?.to_ascii_lowercase();
    if name.ends_with(".py") {
        Some("python")
    } else if name.ends_with(".js")
        || name.ends_with(".ts")
        || name.ends_with(".jsx")
        || name.ends_with(".tsx")
        || name.ends_with(".mjs")
        || name.ends_with(".cjs")
        || name.ends_with(".mts")
        || name.ends_with(".cts")
    {
        Some("javascript")
    } else if name.ends_with(".rs") {
        Some("rust")
    } else if name.ends_with(".go") {
        Some("go")
    } else if name.ends_with(".c")
        || name.ends_with(".h")
        || name.ends_with(".cpp")
        || name.ends_with(".cc")
        || name.ends_with(".cxx")
        || name.ends_with(".hpp")
        || name.ends_with(".hh")
    {
        Some("c")
    } else if name.ends_with(".cs") {
        Some("csharp")
    } else if name.ends_with(".java") {
        Some("java")
    } else {
        None
    }
}

/// Read source as text. Invalid UTF-8 is decoded lossily so ASCII imports survive,
/// and the warning is returned for the JSON result instead of a silent empty file.
pub fn read_utf8(path: &Path) -> (String, Option<String>) {
    let bytes = match fs::read(path) {
        Ok(bytes) => bytes,
        Err(err) => return (String::new(), Some(format!("unreadable: {err}"))),
    };
    match String::from_utf8(bytes) {
        Ok(text) => (text, None),
        Err(err) => {
            let text = String::from_utf8_lossy(err.as_bytes()).into_owned();
            (text, Some("not valid UTF-8; parsed with lossy replacement so ASCII imports are kept".into()))
        }
    }
}

fn scan_text(path: &Path, text: &str) -> Scan {
    match language(path) {
        Some("python") => scan_python(text),
        Some("javascript") => scan_js(text),
        Some("rust") => scan_rust(text),
        Some("go") => scan_go(text),
        Some("c") => scan_c(text),
        Some("csharp") => scan_csharp(text),
        Some("java") => scan_java(text),
        _ => Scan::default(),
    }
}

/// Scan one file. A parser panic becomes an empty scan plus a warning so one bad file
/// cannot abort the rest of the map.
pub fn scan_file_warned(path: &Path) -> (Scan, String, Option<String>) {
    let (text, warning) = read_utf8(path);
    let parsed = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| scan_text(path, &text)));
    match parsed {
        Ok(scan) => (scan, text, warning),
        Err(_) => {
            let fail = "parser failed; file skipped so the rest of the map can continue".to_string();
            let warning = Some(match warning {
                Some(prev) => format!("{prev}; {fail}"),
                None => fail,
            });
            (Scan::default(), text, warning)
        }
    }
}

pub fn scan_file(path: &Path) -> Scan {
    scan_file_warned(path).0
}

pub fn resolve_project(root: &Path, files: &[PathBuf]) -> BTreeMap<String, BTreeSet<String>> {
    let mut scans: BTreeMap<String, Scan> = BTreeMap::new();
    let mut rels = Vec::new();
    for f in files {
        let rel = rel_of(root, f);
        scans.insert(rel.clone(), scan_file(f));
        rels.push(rel);
    }
    let resolver = Resolver::build(root, &rels);
    let mut edges: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for rel in &rels {
        let scan = scans.get(rel).cloned().unwrap_or_default();
        let mut dsts = BTreeSet::new();
        let lang = language(Path::new(rel)).unwrap_or("");
        for imp in &scan.imports {
            if let Some(target) = resolver.resolve(rel, &imp.spec, lang) {
                if &target != rel {
                    dsts.insert(target.clone());
                }
                if lang == "javascript" && (imp.kind == Kind::Import || imp.kind == Kind::ExportFrom) && !imp.names.is_empty() {
                    for name in &imp.names {
                        if let Some(def) = defining_file(&resolver, &scans, &target, name, 0) {
                            if &def != rel && def != target {
                                dsts.insert(def);
                            }
                        }
                    }
                }
            }
        }
        edges.insert(rel.clone(), dsts);
    }
    edges
}

fn defining_file(resolver: &Resolver, scans: &BTreeMap<String, Scan>, file: &str, name: &str, depth: usize) -> Option<String> {
    if depth > 8 {
        return Some(file.to_string());
    }
    let scan = scans.get(file)?;
    if scan.local_exports.iter().any(|n| n == name) {
        return Some(file.to_string());
    }
    for imp in &scan.imports {
        if imp.kind == Kind::ExportFrom && imp.names.iter().any(|n| n == name) {
            let target = resolver.resolve(file, &imp.spec, "javascript")?;
            return defining_file(resolver, scans, &target, name, depth + 1).or(Some(target));
        }
    }
    for imp in &scan.imports {
        if imp.kind == Kind::ExportStar {
            if let Some(target) = resolver.resolve(file, &imp.spec, "javascript") {
                if let Some(found) = defining_file(resolver, scans, &target, name, depth + 1) {
                    return Some(found);
                }
            }
        }
    }
    None
}

struct Resolver {
    files: BTreeSet<String>,
    ts_paths: Vec<(String, String, String)>,
    packages: Vec<Package>,
}

struct Package {
    dir: String,
    name: String,
    exports: Vec<(String, String)>,
}

impl Resolver {
    fn build(root: &Path, rels: &[String]) -> Self {
        let files: BTreeSet<String> = rels.iter().cloned().collect();
        let ts_paths = load_ts_paths(root);
        let packages = load_packages(root);
        Resolver { files, ts_paths, packages }
    }

    fn resolve(&self, from_rel: &str, spec: &str, lang: &str) -> Option<String> {
        match lang {
            "python" => None, // python resolves inside scan_python via statements; handled below
            "javascript" => self.resolve_js(from_rel, spec),
            "rust" => self.resolve_rust(from_rel, spec),
            "go" => self.resolve_go(from_rel, spec),
            "c" => self.resolve_c(from_rel, spec),
            "java" => self.resolve_java(spec),
            "csharp" => self.resolve_csharp(spec),
            _ => None,
        }
    }

    fn resolve_js(&self, from_rel: &str, spec: &str) -> Option<String> {
        if spec.starts_with('.') {
            let base = Path::new(from_rel).parent().unwrap_or(Path::new(""));
            return self.relative_file(base, spec);
        }
        if let Some(hit) = self.apply_paths(spec) {
            return Some(hit);
        }
        self.apply_package(spec)
    }

    fn relative_file(&self, base: &Path, spec: &str) -> Option<String> {
        let joined = normalize(&base.join(spec));
        self.try_extensions(&joined)
    }

    fn try_extensions(&self, rel_no_ext: &str) -> Option<String> {
        let as_is = rel_no_ext.trim_start_matches("./").to_string();
        if self.files.contains(&as_is) {
            return Some(as_is);
        }
        const EXTS: &[&str] = &[".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".d.ts"];
        for ext in EXTS {
            let cand = format!("{as_is}{ext}");
            if self.files.contains(&cand) {
                return Some(cand);
            }
        }
        for ext in EXTS {
            let cand = format!("{as_is}/index{ext}");
            if self.files.contains(&cand) {
                return Some(cand);
            }
        }
        None
    }

    fn apply_paths(&self, spec: &str) -> Option<String> {
        let mut best: Option<(usize, String)> = None;
        for (pattern, replacement, base) in &self.ts_paths {
            if let Some(rest) = match_star(pattern, spec) {
                let mut target = replacement.replace('*', &rest);
                if !target.starts_with('.') && !target.starts_with('/') {
                    target = format!("{}/{}", base.trim_end_matches('/'), target.trim_start_matches('/'));
                }
                target = normalize(Path::new(&target));
                if let Some(hit) = self.try_extensions(&target) {
                    let score = pattern.len();
                    if best.as_ref().map(|(s, _)| score > *s).unwrap_or(true) {
                        best = Some((score, hit));
                    }
                }
            }
        }
        best.map(|(_, h)| h)
    }

    fn apply_package(&self, spec: &str) -> Option<String> {
        for pkg in &self.packages {
            if spec != pkg.name && !spec.starts_with(&(pkg.name.clone() + "/")) {
                continue;
            }
            let sub = if spec == pkg.name { ".".to_string() } else { format!("./{}", &spec[pkg.name.len() + 1..]) };
            let mapped = pkg.exports.iter().find(|(k, _)| k == &sub).map(|(_, v)| v.clone())
                .or_else(|| if sub == "." { pkg.exports.iter().find(|(k, _)| k == ".").map(|(_, v)| v.clone()) } else { None });
            let rel_target = if let Some(m) = mapped {
                normalize(&Path::new(&pkg.dir).join(m.trim_start_matches("./")))
            } else {
                normalize(&Path::new(&pkg.dir).join(sub.trim_start_matches("./")))
            };
            if let Some(hit) = self.try_extensions(&rel_target) {
                return Some(hit);
            }
        }
        None
    }

    fn resolve_rust(&self, from_rel: &str, spec: &str) -> Option<String> {
        if let Some(rest) = spec.strip_prefix("mod:") {
            let base = Path::new(from_rel).parent().unwrap_or(Path::new(""));
            let a = normalize(&base.join(format!("{rest}.rs")));
            if self.files.contains(&a) {
                return Some(a);
            }
            let b = normalize(&base.join(rest).join("mod.rs"));
            if self.files.contains(&b) {
                return Some(b);
            }
            return None;
        }
        if let Some(rest) = spec.strip_prefix("crate::") {
            let parts: Vec<&str> = rest.split("::").filter(|p| !p.is_empty()).collect();
            return self.rust_under("src", &parts).or_else(|| self.rust_under("", &parts));
        }
        None
    }

    fn rust_under(&self, prefix: &str, parts: &[&str]) -> Option<String> {
        if parts.is_empty() {
            return None;
        }
        let mut p = PathBuf::from(prefix);
        for part in parts {
            p.push(part);
        }
        let file = normalize(&p).trim_end_matches('/').to_string() + ".rs";
        if self.files.contains(&file) {
            return Some(file);
        }
        let dirmod = normalize(&p.join("mod.rs"));
        if self.files.contains(&dirmod) {
            return Some(dirmod);
        }
        if parts.len() > 1 {
            return self.rust_under(prefix, &parts[..parts.len() - 1]);
        }
        None
    }

    fn resolve_go(&self, from_rel: &str, spec: &str) -> Option<String> {
        if spec.starts_with('.') {
            let base = Path::new(from_rel).parent().unwrap_or(Path::new(""));
            let joined = normalize(&base.join(spec));
            let exact = format!("{joined}.go");
            if self.files.contains(&exact) {
                return Some(exact);
            }
            let prefix = format!("{joined}/");
            return self.files.iter().find(|f| f.starts_with(&prefix) && f.ends_with(".go")).cloned();
        }
        let tail = spec.rsplit('/').next().unwrap_or(spec);
        let exact = format!("{tail}.go");
        let suffix = format!("/{tail}.go");
        self.files.iter().find(|f| f.ends_with(&suffix) || f.as_str() == exact).cloned()
    }

    fn resolve_c(&self, from_rel: &str, spec: &str) -> Option<String> {
        let base = Path::new(from_rel).parent().unwrap_or(Path::new(""));
        let direct = normalize(&base.join(spec));
        if self.files.contains(&direct) {
            return Some(direct);
        }
        for sub in ["include", "inc", "src"] {
            let cand = normalize(&base.join(sub).join(spec));
            if self.files.contains(&cand) {
                return Some(cand);
            }
        }
        let name = Path::new(spec).file_name()?.to_string_lossy().to_string();
        self.files.iter().find(|f| f.ends_with(&format!("/{name}")) || f.as_str() == name).cloned()
    }

    fn resolve_java(&self, spec: &str) -> Option<String> {
        let class = spec.split('.').next_back()?.trim();
        if class.is_empty() || class == "*" {
            return None;
        }
        let suffix = format!("/{class}.java");
        let exact = format!("{class}.java");
        self.files.iter().find(|f| f.ends_with(&suffix) || f.as_str() == exact).cloned()
    }

    fn resolve_csharp(&self, spec: &str) -> Option<String> {
        let name = spec.split('.').next_back()?.trim();
        let suffix = format!("/{name}.cs");
        let exact = format!("{name}.cs");
        self.files.iter().find(|f| f.ends_with(&suffix) || f.as_str() == exact).cloned()
    }
}

fn match_star(pattern: &str, spec: &str) -> Option<String> {
    if let Some((pre, post)) = pattern.split_once('*') {
        if spec.starts_with(pre) && spec.ends_with(post) && spec.len() >= pre.len() + post.len() {
            let mid = &spec[pre.len()..spec.len() - post.len()];
            return Some(mid.to_string());
        }
        None
    } else if pattern == spec {
        Some(String::new())
    } else {
        None
    }
}

fn normalize(path: &Path) -> String {
    let mut stack: Vec<String> = Vec::new();
    for c in path.components() {
        match c {
            std::path::Component::CurDir => {}
            std::path::Component::ParentDir => {
                stack.pop();
            }
            std::path::Component::Normal(s) => stack.push(s.to_string_lossy().to_string()),
            _ => {}
        }
    }
    stack.join("/")
}

fn load_ts_paths(root: &Path) -> Vec<(String, String, String)> {
    let text = fs::read_to_string(root.join("tsconfig.json")).unwrap_or_default();
    if text.is_empty() {
        return Vec::new();
    }
    let Ok(json) = jsonutil::parse_jsonc(&text) else { return Vec::new() };
    let base = json.get("compilerOptions").and_then(|c| c.get("baseUrl")).and_then(|b| b.as_str()).unwrap_or(".").trim_end_matches('/').to_string();
    let mut out = Vec::new();
    let Some(paths) = json.get("compilerOptions").and_then(|c| c.get("paths")).and_then(|p| p.as_object()) else {
        return out;
    };
    for (pat, val) in paths {
        let repl = match val {
            Json::Array(a) => a.first().and_then(|v| v.as_str()).unwrap_or(""),
            Json::String(s) => s,
            _ => "",
        };
        if !repl.is_empty() {
            out.push((pat.clone(), repl.to_string(), base.clone()));
        }
    }
    out
}

fn load_packages(root: &Path) -> Vec<Package> {
    let mut dirs = vec![root.to_path_buf()];
    if let Ok(text) = fs::read_to_string(root.join("package.json")) {
        if let Ok(json) = jsonutil::parse(&text) {
            if let Some(ws) = json.get("workspaces").and_then(|w| w.as_array()) {
                for item in ws {
                    if let Some(pat) = item.as_str() {
                        if let Some(prefix) = pat.strip_suffix("/*") {
                            if let Ok(rd) = fs::read_dir(root.join(prefix)) {
                                for ent in rd.flatten() {
                                    if ent.path().is_dir() {
                                        dirs.push(ent.path());
                                    }
                                }
                            }
                        } else {
                            dirs.push(root.join(pat));
                        }
                    }
                }
            }
        }
    }
    let mut pkgs = Vec::new();
    for dir in dirs {
        let text = fs::read_to_string(dir.join("package.json")).unwrap_or_default();
        let Ok(json) = jsonutil::parse(&text) else { continue };
        let Some(name) = json.get("name").and_then(|n| n.as_str()) else { continue };
        let mut exports = Vec::new();
        if let Some(exp) = json.get("exports") {
            collect_exports(exp, &mut exports);
        }
        let rel_dir = rel_of(root, &dir);
        let rel_dir = if rel_dir.is_empty() { ".".to_string() } else { rel_dir };
        pkgs.push(Package { dir: rel_dir, name: name.to_string(), exports });
    }
    pkgs
}

fn collect_exports(exp: &Json, out: &mut Vec<(String, String)>) {
    match exp {
        Json::String(s) => out.push((".".into(), s.clone())),
        Json::Object(map) => {
            for (k, v) in map {
                match v {
                    Json::String(s) => out.push((k.clone(), s.clone())),
                    Json::Object(inner) => {
                        let pref = ["import", "default", "require", "types", "node"]
                            .iter()
                            .find_map(|key| inner.get(*key).and_then(|x| x.as_str()));
                        if let Some(s) = pref {
                            out.push((k.clone(), s.to_string()));
                        } else if let Some((_, s)) = inner.iter().find_map(|(_, val)| val.as_str().map(|s| ((), s.to_string()))) {
                            out.push((k.clone(), s));
                        }
                    }
                    _ => {}
                }
            }
        }
        _ => {}
    }
}

fn scan_python(src: &str) -> Scan {
    let (masked, dynamic) = mask_python(src);
    let mut imports = Vec::new();
    for spec in dynamic {
        imports.push(RawImport { spec, names: Vec::new(), kind: Kind::Dynamic });
    }
    for stmt in python_statements(&masked) {
        imports.push(stmt);
    }
    Scan { imports, local_exports: Vec::new() }
}

fn mask_python(src: &str) -> (String, Vec<String>) {
    let b = src.as_bytes();
    let mut out = String::with_capacity(src.len());
    let mut dynamic = Vec::new();
    let mut i = 0;
    let mut code_tail = String::new();
    while i < b.len() {
        if !src.is_char_boundary(i) {
            i += 1;
            continue;
        }
        if b[i] == b'#' {
            while i < b.len() && b[i] != b'\n' {
                let n = utf8_len(src, i);
                out.push(' ');
                i += n;
            }
            continue;
        }
        if python_quote_at(b, i).is_some() {
            let (q, body_start) = quote_span(b, i);
            let mut j = body_start;
            while j + q.len() <= b.len() && &b[j..j + q.len()] != q.as_slice() {
                if b[j] == b'\\' && q.len() == 1 {
                    j += 2;
                    continue;
                }
                j += 1;
            }
            let body = String::from_utf8_lossy(&b[body_start..j]).into_owned();
            let recent = recent_call(&code_tail);
            if recent == "import_module" || recent == "__import__" {
                let lit = body.trim();
                if is_py_module_lit(lit) {
                    dynamic.push(lit.to_string());
                }
            }
            let end = align_boundary(src, (j + q.len()).min(b.len())).max(i);
            for ch in src[i..end].chars() {
                out.push(if ch == '\n' { '\n' } else { ' ' });
            }
            i = end;
            code_tail.clear();
            continue;
        }
        let ch = src[i..].chars().next().unwrap();
        out.push(ch);
        push_code_tail(&mut code_tail, ch);
        i += ch.len_utf8();
    }
    (out, dynamic)
}

fn utf8_len(src: &str, i: usize) -> usize {
    src[i..].chars().next().map(|ch| ch.len_utf8()).unwrap_or(1)
}

fn align_boundary(src: &str, mut end: usize) -> usize {
    if end > src.len() {
        end = src.len();
    }
    while end < src.len() && !src.is_char_boundary(end) {
        end += 1;
    }
    end
}

fn push_code_tail(tail: &mut String, ch: char) {
    tail.push(ch);
    const MAX: usize = 80;
    let count = tail.chars().count();
    if count <= MAX {
        return;
    }
    let mut cut = 0;
    for (n, ch) in tail.chars().enumerate() {
        if n == count - MAX {
            break;
        }
        cut += ch.len_utf8();
    }
    *tail = tail[cut..].to_string();
}

fn recent_call(tail: &str) -> &str {
    let t = tail.trim_end();
    let t = t.trim_end_matches('(').trim_end();
    if t.ends_with("import_module") {
        "import_module"
    } else if t.ends_with("__import__") {
        "__import__"
    } else {
        ""
    }
}

fn is_py_module_lit(s: &str) -> bool {
    !s.is_empty() && s.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '.')
}

fn python_quote_at(b: &[u8], i: usize) -> Option<usize> {
    let (q, body) = quote_span(b, i);
    if q.is_empty() {
        None
    } else {
        Some(body - i)
    }
}

fn quote_span(b: &[u8], i: usize) -> (Vec<u8>, usize) {
    let mut k = i;
    // prefixes
    let start = i;
    while k < b.len() && matches!(b[k], b'r' | b'R' | b'f' | b'F' | b'b' | b'B' | b'u' | b'U') {
        k += 1;
        if k - start > 3 {
            break;
        }
    }
    if k >= b.len() || (b[k] != b'\'' && b[k] != b'"') {
        return (Vec::new(), i);
    }
    // prefix must be bounded
    if start > 0 {
        let prev = b[start - 1];
        if prev.is_ascii_alphanumeric() || prev == b'_' {
            return (Vec::new(), i);
        }
    }
    let q = b[k];
    let triple = k + 2 < b.len() && b[k + 1] == q && b[k + 2] == q;
    let quote = if triple { vec![q, q, q] } else { vec![q] };
    let body = k + quote.len();
    (quote, body)
}

fn python_statements(masked: &str) -> Vec<RawImport> {
    // Python resolution is not a string spec. Encode statements as `py:<kind>:<level>:<module>:<names>`
    let mut out = Vec::new();
    let lines: Vec<&str> = masked.lines().collect();
    let mut i = 0;
    while i < lines.len() {
        let line = lines[i].trim();
        if line.starts_with("import ") || line.starts_with("from ") {
            let mut buf = line.to_string();
            let mut depth = paren_delta(line);
            while depth > 0 && i + 1 < lines.len() {
                i += 1;
                buf.push(' ');
                buf.push_str(lines[i].trim());
                depth += paren_delta(lines[i]);
            }
            if let Some(imp) = parse_py_stmt(&buf) {
                out.push(imp);
            }
        }
        i += 1;
    }
    out
}

fn paren_delta(s: &str) -> i32 {
    s.chars().fold(0, |n, c| n + match c { '(' => 1, ')' => -1, _ => 0 })
}

fn parse_py_stmt(stmt: &str) -> Option<RawImport> {
    let stmt = stmt.trim().trim_end_matches('\\').trim();
    if let Some(rest) = stmt.strip_prefix("import ") {
        let names = rest.split(',').map(|s| s.trim().split_whitespace().next().unwrap_or("")).filter(|s| !s.is_empty() && *s != "__future__").collect::<Vec<_>>().join(",");
        if names.is_empty() {
            return None;
        }
        return Some(RawImport { spec: format!("py:import:0::{names}"), names: Vec::new(), kind: Kind::Import });
    }
    if let Some(rest) = stmt.strip_prefix("from ") {
        let import_at = rest.find(" import ")?;
        let left = rest[..import_at].trim();
        let right = rest[import_at + " import ".len()..].trim().trim_matches(|c| c == '(' || c == ')');
        let mut level = 0;
        for c in left.chars() {
            if c == '.' {
                level += 1;
            } else {
                break;
            }
        }
        let module = left[level..].trim();
        let names: Vec<String> = right
            .split(',')
            .map(|s| s.trim().split_whitespace().next().unwrap_or("").to_string())
            .filter(|s| !s.is_empty())
            .collect();
        if module.starts_with("__future__") {
            return None;
        }
        return Some(RawImport {
            spec: format!("py:from:{level}:{module}:{}", names.join(",")),
            names,
            kind: Kind::Import,
        });
    }
    None
}

fn scan_js(src: &str) -> Scan {
    let b = src.as_bytes();
    let mut i = 0;
    let mut imports = Vec::new();
    let mut local_exports = Vec::new();
    let mut tail = String::new();
    while i < b.len() {
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
            i = skip_js_string(b, i);
            tail.push(' ');
            continue;
        }
        if b[i] == b'`' {
            i = scan_template(b, i, &mut imports, &mut local_exports);
            continue;
        }
        if b[i] == b'/' && js_regex_start(&tail) {
            i += 1;
            while i < b.len() && b[i] != b'/' && b[i] != b'\n' {
                if b[i] == b'\\' {
                    i += 2;
                    continue;
                }
                i += 1;
            }
            if i < b.len() && b[i] == b'/' {
                i += 1;
            }
            tail.push(' ');
            continue;
        }
        if starts_word(b, i, "import") {
            let after = i + "import".len();
            if after < b.len() && b[after] == b'(' {
                if let Some((spec, next)) = read_call_spec(src, after) {
                    imports.push(RawImport { spec, names: Vec::new(), kind: Kind::Dynamic });
                    i = next;
                    tail.clear();
                    continue;
                }
            }
            if let Some((imp, n)) = read_import_statement(&src[after..]) {
                imports.push(imp);
                i = after + n;
                tail.clear();
                continue;
            }
        }
        if starts_word(b, i, "export") {
            let rest = &src[i + "export".len()..];
            let trimmed = rest.trim_start();
            let lead = rest.len() - trimmed.len();
            if trimmed.starts_with('*') || (trimmed.starts_with('{') && trimmed.contains(" from ")) {
                if let Some((imp, n)) = read_export_from(trimmed) {
                    imports.push(imp);
                    i = i + "export".len() + lead + n;
                    tail.clear();
                    continue;
                }
            } else if let Some(name) = export_local_name(trimmed) {
                local_exports.push(name);
                i += "export".len();
                continue;
            }
        }
        if starts_word(b, i, "require") {
            let after = i + "require".len();
            if after < b.len() && b[after] == b'(' {
                if let Some((spec, next)) = read_call_spec(src, after) {
                    imports.push(RawImport { spec, names: Vec::new(), kind: Kind::Dynamic });
                    i = next;
                    tail.clear();
                    continue;
                }
            }
        }
        if !src.is_char_boundary(i) {
            i += 1;
            continue;
        }
        let ch = src[i..].chars().next().unwrap();
        tail.push(ch);
        while tail.chars().count() > 12 {
            tail.remove(0);
        }
        i += ch.len_utf8();
    }
    Scan { imports, local_exports }
}

fn scan_template(b: &[u8], mut i: usize, imports: &mut Vec<RawImport>, local_exports: &mut Vec<String>) -> usize {
    i += 1;
    while i < b.len() && b[i] != b'`' {
        if b[i] == b'$' && i + 1 < b.len() && b[i + 1] == b'{' {
            i += 2;
            let start = i;
            let mut depth = 1;
            while i < b.len() && depth > 0 {
                if b[i] == b'{' {
                    depth += 1;
                } else if b[i] == b'}' {
                    depth -= 1;
                    if depth == 0 {
                        break;
                    }
                } else if b[i] == b'\'' || b[i] == b'"' || b[i] == b'`' {
                    i = skip_js_string(b, i);
                    continue;
                }
                i += 1;
            }
            let expr = String::from_utf8_lossy(&b[start..i]).to_string();
            let inner = scan_js(&expr);
            imports.extend(inner.imports);
            local_exports.extend(inner.local_exports);
            if i < b.len() && b[i] == b'}' {
                i += 1;
            }
            continue;
        }
        i += 1;
    }
    if i < b.len() && b[i] == b'`' {
        i += 1;
    }
    i
}

fn export_local_name(trimmed: &str) -> Option<String> {
    let rest = trimmed.trim_start_matches("default ").trim_start();
    for kw in ["const ", "let ", "var ", "function ", "async function ", "class ", "interface ", "type ", "enum "] {
        if let Some(after) = rest.strip_prefix(kw) {
            let name = after.split(['=', '(', '<', '{', ':', ' ', '\n', '\t']).next().unwrap_or("");
            if is_ident(name) {
                return Some(name.to_string());
            }
        }
    }
    if rest.starts_with('{') && !rest.contains(" from ") {
        return brace_names(rest).into_iter().next();
    }
    None
}

fn js_regex_start(code: &str) -> bool {
    let t = code.trim_end();
    t.is_empty() || t.ends_with(['=', '(', '[', ',', ';', '!', '&', '|', '?', ':', '{', '}', '+', '-'])
}

fn skip_js_string(b: &[u8], i: usize) -> usize {
    let q = b[i];
    let mut j = i + 1;
    while j < b.len() {
        if b[j] == b'\\' {
            j += 2;
            continue;
        }
        if b[j] == q {
            return j + 1;
        }
        j += 1;
    }
    b.len()
}

fn is_ident(s: &str) -> bool {
    let mut cs = s.chars();
    match cs.next() {
        Some(c) if c.is_ascii_alphabetic() || c == '_' || c == '$' => cs.all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '$'),
        _ => false,
    }
}

fn starts_word(b: &[u8], i: usize, word: &str) -> bool {
    let w = word.as_bytes();
    if i + w.len() > b.len() || &b[i..i + w.len()] != w {
        return false;
    }
    let before_ok = i == 0 || !is_word(b[i - 1]);
    let after_ok = i + w.len() == b.len() || !is_word(b[i + w.len()]);
    before_ok && after_ok
}

fn is_word(c: u8) -> bool {
    c.is_ascii_alphanumeric() || c == b'_' || c == b'$'
}

fn read_call_spec(code: &str, paren: usize) -> Option<(String, usize)> {
    let bytes = code.as_bytes();
    let mut i = paren + 1;
    while i < bytes.len() && bytes[i].is_ascii_whitespace() {
        i += 1;
    }
    if i >= bytes.len() || (bytes[i] != b'\'' && bytes[i] != b'"') {
        return None;
    }
    let q = bytes[i];
    i += 1;
    let start = i;
    while i < bytes.len() && bytes[i] != q {
        if bytes[i] == b'\\' {
            i += 2;
            continue;
        }
        i += 1;
    }
    let spec = code[start..i].to_string();
    Some((spec, i + 1))
}

fn read_import_statement(rest: &str) -> Option<(RawImport, usize)> {
    let t = rest.trim_start();
    let lead = rest.len() - t.len();
    if t.starts_with('\'') || t.starts_with('"') {
        let (spec, n) = read_quoted(t)?;
        return Some((RawImport { spec, names: Vec::new(), kind: Kind::Import }, lead + n));
    }
    let from = t.find(" from ")?;
    let head = &t[..from];
    let after = &t[from + " from ".len()..];
    let ws = after.len() - after.trim_start().len();
    let (spec, n) = read_quoted(after.trim_start())?;
    let names = brace_names(head);
    Some((RawImport { spec, names, kind: Kind::Import }, lead + from + " from ".len() + ws + n))
}

fn read_export_from(trimmed: &str) -> Option<(RawImport, usize)> {
    if trimmed.starts_with('*') {
        let from = trimmed.find(" from ")?;
        let after = trimmed[from + " from ".len()..].trim_start();
        let (spec, n) = read_quoted(after)?;
        let consumed = from + " from ".len() + (trimmed[from + " from ".len()..].len() - after.len()) + n;
        return Some((RawImport { spec, names: Vec::new(), kind: Kind::ExportStar }, consumed));
    }
    if trimmed.starts_with('{') {
        let from = trimmed.find(" from ")?;
        let names = brace_names(&trimmed[..from]);
        let after = trimmed[from + " from ".len()..].trim_start();
        let (spec, n) = read_quoted(after)?;
        let consumed = from + " from ".len() + (trimmed[from + " from ".len()..].len() - after.len()) + n;
        return Some((RawImport { spec, names, kind: Kind::ExportFrom }, consumed));
    }
    None
}

fn brace_names(head: &str) -> Vec<String> {
    let Some(a) = head.find('{') else { return Vec::new() };
    let Some(b) = head.find('}') else { return Vec::new() };
    head[a + 1..b]
        .split(',')
        .filter_map(|part| {
            let part = part.trim();
            if part.is_empty() {
                return None;
            }
            let name = if let Some((_, right)) = part.split_once(" as ") {
                right.trim()
            } else {
                part.split_whitespace().next().unwrap_or("")
            };
            // `type Foo` inside braces
            let name = name.trim_start_matches("type ").trim();
            if is_ident(name) { Some(name.to_string()) } else { None }
        })
        .collect()
}

fn read_quoted(s: &str) -> Option<(String, usize)> {
    let b = s.as_bytes();
    if b.is_empty() || (b[0] != b'\'' && b[0] != b'"') {
        return None;
    }
    let q = b[0];
    let mut i = 1;
    let mut raw = Vec::new();
    while i < b.len() {
        if b[i] == b'\\' && i + 1 < b.len() {
            raw.push(b[i + 1]);
            i += 2;
            continue;
        }
        if b[i] == q {
            return Some((String::from_utf8_lossy(&raw).into_owned(), i + 1));
        }
        raw.push(b[i]);
        i += 1;
    }
    None
}

fn scan_rust(src: &str) -> Scan {
    let mut imports = Vec::new();
    for line in strip_c_comments(src).lines() {
        let t = line.trim();
        if let Some(rest) = t.strip_prefix("mod ") {
            let name = rest.trim().trim_end_matches(';').split_whitespace().next().unwrap_or("");
            if is_ident(name) {
                imports.push(RawImport { spec: format!("mod:{name}"), names: Vec::new(), kind: Kind::Import });
            }
        } else if let Some(rest) = t.strip_prefix("pub mod ") {
            let name = rest.trim().trim_end_matches(';').split_whitespace().next().unwrap_or("");
            if is_ident(name) {
                imports.push(RawImport { spec: format!("mod:{name}"), names: Vec::new(), kind: Kind::Import });
            }
        } else if let Some(rest) = t.strip_prefix("use ") {
            let rest = rest.trim().trim_end_matches(';');
            if rest.starts_with("crate::") {
                let path = rest.split("::").take_while(|p| !p.contains('{') && !p.contains(' ')).collect::<Vec<_>>().join("::");
                // drop the last segment if it looks like an item (lowercase function) — keep module path
                imports.push(RawImport { spec: path, names: Vec::new(), kind: Kind::Import });
            }
        }
    }
    Scan { imports, local_exports: Vec::new() }
}

fn scan_go(src: &str) -> Scan {
    let mut imports = Vec::new();
    let text = strip_c_comments(src);
    let bytes = text.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if starts_word(bytes, i, "import") {
            let mut j = i + "import".len();
            while j < bytes.len() && bytes[j].is_ascii_whitespace() {
                j += 1;
            }
            if j < bytes.len() && bytes[j] == b'(' {
                j += 1;
                while j < bytes.len() && bytes[j] != b')' {
                    if bytes[j] == b'"' {
                        if let Some((spec, n)) = read_quoted(&text[j..]) {
                            imports.push(RawImport { spec, names: Vec::new(), kind: Kind::Import });
                            j += n;
                            continue;
                        }
                    }
                    j += 1;
                }
                i = j;
                continue;
            }
            if j < bytes.len() && bytes[j] == b'"' {
                if let Some((spec, n)) = read_quoted(&text[j..]) {
                    imports.push(RawImport { spec, names: Vec::new(), kind: Kind::Import });
                    i = j + n;
                    continue;
                }
            }
        }
        i += 1;
    }
    Scan { imports, local_exports: Vec::new() }
}

fn scan_c(src: &str) -> Scan {
    let mut imports = Vec::new();
    for line in strip_c_comments(src).lines() {
        let t = line.trim();
        if let Some(rest) = t.strip_prefix("#include") {
            let rest = rest.trim();
            if let Some(inner) = rest.strip_prefix('"').and_then(|r| r.strip_suffix('"')) {
                imports.push(RawImport { spec: inner.to_string(), names: Vec::new(), kind: Kind::Import });
            } else if let Some(inner) = rest.strip_prefix('<').and_then(|r| r.strip_suffix('>')) {
                imports.push(RawImport { spec: inner.to_string(), names: Vec::new(), kind: Kind::Import });
            }
        }
    }
    Scan { imports, local_exports: Vec::new() }
}

fn scan_java(src: &str) -> Scan {
    let mut imports = Vec::new();
    for line in strip_c_comments(src).lines() {
        let t = line.trim().trim_end_matches(';').trim();
        if let Some(rest) = t.strip_prefix("import ") {
            let rest = rest.trim_start_matches("static ").trim();
            if !rest.is_empty() {
                imports.push(RawImport { spec: rest.to_string(), names: Vec::new(), kind: Kind::Import });
            }
        }
    }
    Scan { imports, local_exports: Vec::new() }
}

fn scan_csharp(src: &str) -> Scan {
    let mut imports = Vec::new();
    for line in strip_c_comments(src).lines() {
        let t = line.trim().trim_end_matches(';').trim();
        if let Some(rest) = t.strip_prefix("using ") {
            let rest = rest.trim();
            if rest.starts_with("static ") || rest.contains('=') {
                continue;
            }
            if !rest.is_empty() && !rest.starts_with('(') {
                imports.push(RawImport { spec: rest.to_string(), names: Vec::new(), kind: Kind::Import });
            }
        }
    }
    Scan { imports, local_exports: Vec::new() }
}

fn strip_c_comments(src: &str) -> String {
    let b = src.as_bytes();
    let mut out = String::with_capacity(src.len());
    let mut i = 0;
    while i < b.len() {
        if b[i] == b'/' && i + 1 < b.len() && b[i + 1] == b'/' {
            while i < b.len() && b[i] != b'\n' {
                i += 1;
            }
            continue;
        }
        if b[i] == b'/' && i + 1 < b.len() && b[i + 1] == b'*' {
            i += 2;
            while i + 1 < b.len() && !(b[i] == b'*' && b[i + 1] == b'/') {
                if b[i] == b'\n' {
                    out.push('\n');
                }
                i += 1;
            }
            i = (i + 2).min(b.len());
            continue;
        }
        if b[i] == b'"' || b[i] == b'\'' {
            let q = b[i];
            out.push(q as char);
            i += 1;
            while i < b.len() && b[i] != q {
                out.push(b[i] as char);
                if b[i] == b'\\' {
                    i += 1;
                    if i < b.len() {
                        out.push(b[i] as char);
                    }
                }
                i += 1;
            }
            if i < b.len() {
                out.push(b[i] as char);
                i += 1;
            }
            continue;
        }
        out.push(b[i] as char);
        i += 1;
    }
    out
}

/// Python statement specs are resolved here, not by the generic string resolver.
pub fn resolve_python_spec(root: &Path, from_rel: &str, spec: &str) -> Vec<String> {
    if let Some(rest) = spec.strip_prefix("py:import:") {
        // py:import:0::a.b,c
        let names = rest.split("::").nth(1).unwrap_or("");
        let from = root.join(from_rel);
        let mut out = Vec::new();
        for name in names.split(',') {
            if let Some(p) = py_resolve(&from, root, name, 0) {
                let rel = rel_of(root, &p);
                if rel != from_rel {
                    out.push(rel);
                }
            }
        }
        return out;
    }
    if let Some(rest) = spec.strip_prefix("py:from:") {
        // level:module:names
        let mut parts = rest.splitn(3, ':');
        let level: usize = parts.next().unwrap_or("0").parse().unwrap_or(0);
        let module = parts.next().unwrap_or("");
        let names = parts.next().unwrap_or("");
        let from = root.join(from_rel);
        let name_list: Vec<&str> = names.split(',').filter(|s| !s.is_empty()).collect();
        let mut subs = Vec::new();
        for name in &name_list {
            if *name == "*" {
                continue;
            }
            let dotted = if module.is_empty() { (*name).to_string() } else { format!("{module}.{name}") };
            if let Some(p) = py_resolve(&from, root, &dotted, level) {
                subs.push(rel_of(root, &p));
            }
        }
        let container = py_resolve(&from, root, module, level).map(|p| rel_of(root, &p));
        let concrete: Vec<&str> = name_list.iter().copied().filter(|n| *n != "*").collect();
        let all_subs = !concrete.is_empty() && subs.len() == concrete.len();
        let mut out = Vec::new();
        if all_subs {
            out.extend(subs);
        } else {
            if let Some(c) = container {
                if c != from_rel {
                    out.push(c);
                }
            }
            for s in subs {
                if s != from_rel && !out.contains(&s) {
                    out.push(s);
                }
            }
        }
        out.retain(|r| r != from_rel);
        return out;
    }
    if spec.starts_with("py:") {
        return Vec::new();
    }
    // dynamic module string
    let from = root.join(from_rel);
    py_resolve(&from, root, spec, 0).map(|p| vec![rel_of(root, &p)]).unwrap_or_default()
}

fn py_resolve(from: &Path, root: &Path, module: &str, level: usize) -> Option<PathBuf> {
    if level > 0 {
        return module_file(&relative_base(from, level), module);
    }
    for base in py_search_roots(from, root) {
        if let Some(hit) = module_file(&base, module) {
            return Some(hit);
        }
    }
    None
}

fn relative_base(path: &Path, level: usize) -> PathBuf {
    let mut base = path.parent().unwrap_or(path).to_path_buf();
    for _ in 0..level.saturating_sub(1) {
        if let Some(p) = base.parent() {
            base = p.to_path_buf();
        }
    }
    base
}

fn py_search_roots(path: &Path, project: &Path) -> Vec<PathBuf> {
    let mut top = path.parent().unwrap_or(path).to_path_buf();
    while top.join("__init__.py").is_file() {
        if let Some(parent) = top.parent() {
            if parent == top {
                break;
            }
            top = parent.to_path_buf();
        } else {
            break;
        }
    }
    let mut roots = Vec::new();
    for c in [top, project.to_path_buf(), project.join("src")] {
        if c.is_dir() && !roots.contains(&c) {
            roots.push(c);
        }
    }
    roots
}

fn module_file(base: &Path, dotted: &str) -> Option<PathBuf> {
    let parts: Vec<&str> = dotted.split('.').filter(|p| !p.is_empty()).collect();
    if parts.is_empty() {
        let init = base.join("__init__.py");
        return init.is_file().then_some(init);
    }
    let mut target = base.to_path_buf();
    for p in &parts {
        target.push(p);
    }
    let py = {
        let mut t = target.clone();
        let name = format!("{}.py", t.file_name()?.to_string_lossy());
        t.set_file_name(name);
        t
    };
    let init = target.join("__init__.py");
    let pyi = {
        let mut t = target.clone();
        let name = format!("{}.pyi", t.file_name()?.to_string_lossy());
        t.set_file_name(name);
        t
    };
    for cand in [py, init, pyi] {
        if exists_exact(base, &cand) {
            return Some(cand);
        }
    }
    None
}

fn exists_exact(base: &Path, candidate: &Path) -> bool {
    if !candidate.is_file() {
        return false;
    }
    let Ok(rel) = candidate.strip_prefix(base) else { return candidate.is_file() };
    let mut current = base.to_path_buf();
    for name in rel.components() {
        let name = name.as_os_str().to_string_lossy().to_string();
        let Ok(rd) = fs::read_dir(&current) else { return false };
        let mut found = false;
        for ent in rd.flatten() {
            if ent.file_name().to_string_lossy() == name {
                found = true;
                break;
            }
        }
        if !found {
            return false;
        }
        current.push(&name);
    }
    true
}

#[cfg(test)]
mod dbg_scan {
    #[test]
    fn dynamic_import_spec() {
        let src = "import { add } from '@acme/core';\nimport { log } from '@app/util';\nimport type { Config } from './types';\nconst lazy = () => import('./lazy');\nimport React from 'react';\nlog(add(1, 2));\n";
        let scan = super::scan_js(src);
        assert!(
            scan.imports.iter().any(|i| i.spec == "./lazy"),
            "specs {:?}",
            scan.imports.iter().map(|i| format!("{} {:?}", i.spec, i.kind)).collect::<Vec<_>>()
        );
    }

    #[test]
    fn non_ascii_python_keeps_imports() {
        let mut src = String::new();
        for _ in 0..40 {
            src.push_str("café = \"🐍漢字\"\n");
        }
        src.push_str("from . import b\nimport_module(\"pkg.mod\")\n");
        let scan = super::scan_python(&src);
        assert!(scan.imports.iter().any(|imp| imp.spec.contains("py:from") && imp.spec.contains('b')), "{:?}", scan.imports);
        assert!(scan.imports.iter().any(|imp| imp.spec == "pkg.mod"), "{:?}", scan.imports);
    }

    #[test]
    fn non_ascii_javascript_and_typescript_keep_imports() {
        let mut src = String::new();
        src.push_str("// café 🐍 漢字\n");
        for _ in 0..30 {
            src.push_str("const café = \"🐍漢字\";\n");
        }
        src.push_str("import { add } from \"./math\";\nexport const 値 = 1;\n");
        let scan = super::scan_js(&src);
        assert!(scan.imports.iter().any(|imp| imp.spec == "./math"), "{:?}", scan.imports);
        let ts = "import type { 設定 } from \"./types\";\nconst emoji = \"🐍\";\nexport { 設定 };\n";
        let scan = super::scan_js(ts);
        assert!(scan.imports.iter().any(|imp| imp.spec == "./types"), "{:?}", scan.imports);
    }
}

#[derive(Clone, Debug, Default)]
pub struct FileFacts {
    pub dsts: BTreeSet<String>,
    pub internal: Vec<(String, i64, Vec<String>)>,
    pub external: Vec<String>,
    pub unresolved: Vec<(String, i64)>,
}

pub struct Analysis {
    pub facts: BTreeMap<String, FileFacts>,
    pub scans: HashMap<String, Scan>,
    pub warnings: Vec<String>,
}

fn line_of(text: &str, needles: &[String]) -> i64 {
    for (i, line) in text.lines().enumerate() {
        if needles.iter().any(|n| !n.is_empty() && line.contains(n.as_str())) {
            return (i + 1) as i64;
        }
    }
    1
}

fn py_parts(spec: &str) -> (String, Vec<String>) {
    if let Some(rest) = spec.strip_prefix("py:import:") {
        let names = rest.split("::").nth(1).unwrap_or("").split(',').filter(|s| !s.is_empty()).map(|s| s.to_string()).collect::<Vec<_>>();
        return (names.first().cloned().unwrap_or_default(), names);
    }
    if let Some(rest) = spec.strip_prefix("py:from:") {
        let mut parts = rest.splitn(3, ':');
        let _level = parts.next();
        let module = parts.next().unwrap_or("").to_string();
        let names = parts.next().unwrap_or("").split(',').filter(|s| !s.is_empty()).map(|s| s.to_string()).collect::<Vec<_>>();
        return (module, names);
    }
    (spec.to_string(), Vec::new())
}

pub fn analyze_files(root: &Path, files: &[PathBuf]) -> Analysis {
    let mut scans: HashMap<String, Scan> = HashMap::new();
    let mut texts: HashMap<String, String> = HashMap::new();
    let mut warnings = Vec::new();
    let rels: Vec<String> = files.iter().map(|f| rel_of(root, f)).collect();
    for (f, rel) in files.iter().zip(rels.iter()) {
        let (scan, text, warning) = scan_file_warned(f);
        if let Some(warning) = warning {
            warnings.push(format!("{rel}: {warning}"));
        }
        scans.insert(rel.clone(), scan);
        texts.insert(rel.clone(), text);
    }
    let mut other_files = Vec::new();
    for rel in &rels {
        if language(Path::new(rel)).is_some() && language(Path::new(rel)) != Some("python") {
            other_files.push(root.join(rel));
        }
    }
    let js_edges = resolve_project(root, &other_files);
    let resolver = Resolver::build(root, &rels);
    let mut out = BTreeMap::new();
    for rel in &rels {
        let scan = scans.get(rel).cloned().unwrap_or_default();
        let text = texts.get(rel).cloned().unwrap_or_default();
        let lang = language(Path::new(rel)).unwrap_or("");
        let mut facts = FileFacts::default();
        if lang == "python" {
            for imp in &scan.imports {
                let resolved = resolve_python_spec(root, rel, &imp.spec);
                let (module, names) = py_parts(&imp.spec);
                let mut needles = names.clone();
                if !module.is_empty() {
                    needles.push(module.clone());
                }
                let line = line_of(&text, &needles);
                if resolved.is_empty() {
                    let label = if module.is_empty() { names.first().cloned().unwrap_or_default() } else { module.clone() };
                    if imp.spec.starts_with("py:") {
                        if !label.is_empty() {
                            facts.external.push(label);
                        }
                    } else if !imp.spec.is_empty() {
                        facts.unresolved.push((imp.spec.clone(), line));
                    }
                } else {
                    for dst in resolved {
                        if &dst != rel {
                            facts.dsts.insert(dst.clone());
                            facts.internal.push((dst, line, names.clone()));
                        }
                    }
                }
            }
        } else if !lang.is_empty() {
            for imp in &scan.imports {
                let target = resolver.resolve(rel, &imp.spec, lang);
                let line = line_of(&text, &[imp.spec.clone()]);
                match target {
                    Some(dst) if dst != *rel => {
                        facts.dsts.insert(dst.clone());
                        facts.internal.push((dst.clone(), line, imp.names.clone()));
                        if lang == "javascript" && (imp.kind == Kind::Import || imp.kind == Kind::ExportFrom) {
                            for name in &imp.names {
                                if let Some(def) = defining_file(&resolver, &{
                                    let mut m = BTreeMap::new();
                                    for (k, v) in &scans {
                                        m.insert(k.clone(), v.clone());
                                    }
                                    m
                                }, &dst, name, 0) {
                                    if def != *rel && def != dst && !facts.dsts.contains(&def) {
                                        facts.dsts.insert(def.clone());
                                        facts.internal.push((def, line, vec![name.clone()]));
                                    }
                                }
                            }
                        }
                    }
                    _ => {
                        if imp.spec.starts_with('.') {
                            facts.unresolved.push((imp.spec.clone(), line));
                        } else if !imp.spec.is_empty() && !imp.spec.starts_with("mod:") && !imp.spec.starts_with("crate::") {
                            facts.external.push(imp.spec.clone());
                        } else if imp.spec.starts_with('.') || (target.is_none() && imp.spec.starts_with("mod:")) {
                            facts.unresolved.push((imp.spec.clone(), line));
                        }
                    }
                }
            }
            if let Some(dsts) = js_edges.get(rel) {
                for dst in dsts {
                    if !facts.dsts.contains(dst) {
                        facts.dsts.insert(dst.clone());
                        facts.internal.push((dst.clone(), 1, Vec::new()));
                    }
                }
            }
        }
        facts.external.sort();
        facts.external.dedup();
        out.insert(rel.clone(), facts);
    }
    for rel in &rels {
        out.entry(rel.clone()).or_default();
    }
    let _ = js_edges;
    Analysis { facts: out, scans, warnings }
}

pub fn edges_for_files(root: &Path, files: &[PathBuf]) -> BTreeMap<String, BTreeSet<String>> {
    analyze_files(root, files).facts.into_iter().map(|(k, v)| (k, v.dsts)).collect()
}
